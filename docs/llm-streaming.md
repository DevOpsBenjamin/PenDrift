# LLM Streaming — Design Plan (Backlog)

État actuel : tous les appels LLM passent par `generate_completion` avec
`stream=False` → un POST bloquant à llama-server, on attend le payload JSON
complet, puis on parse. Pas d'affichage token-par-token côté frontend.

L'Activity view affiche des infos live via `/slots` de llama-server (n_past,
n_decoded, tok/s), mais c'est une approximation : résolution 1 s, et on ne voit
pas le contenu généré.

Cette doc décrit le design complet pour passer en streaming SSE bout-en-bout,
avec cut-and-restart pour enforcer le budget de tokens par champ JSON.

---

## Objectifs

1. **Affichage live** : voir la narration s'écrire mot par mot côté frontend
2. **Hard budget par champ** : `thinkingTokens`, `narrativeTokens`,
   `suggestionTokens` du preset deviennent des **limites réelles** et non plus
   une simple somme `max_tokens`
3. **Debuggabilité** : suivre en direct le raisonnement du modèle via l'Activity
   view

## Stack de la chaîne complète

```
llama-server ──SSE──► Python backend (parser JSON incrémental)
                                    ├─► ré-émet SSE ────────► Frontend Vue
                                    └─► cut & restart si budget dépassé
```

## Composants à construire

### 1. Backend : appel streaming à llama-server

Déjà amorcé dans `app/services/llm.py` via `generate_completion_stream` mais
pas câblé. Il faut :
- Passer `stream=True` dans le body envoyé à llama-server
- Consommer le flux SSE (`data: {...}\n\n` par chunk) avec `httpx.stream()`
- Chaque chunk contient un `choices[0].delta.content` avec le nouveau token
- Tenir à jour un buffer cumulé + un compteur de tokens décodés

### 2. Parser JSON incrémental

La grammaire GBNF garantit que la sortie est du JSON valide en fin de course,
mais pendant le stream on a du JSON partiel. Il faut savoir à tout moment :
- Dans quel champ on est (`thinking`, `narrative`, `suggestions`)
- Combien de tokens ce champ a consommés

Implémentation : petite state machine qui suit les guillemets non-échappés et
les `,` au niveau racine. Pas besoin d'un parser JSON complet — juste détecter
les transitions de champ.

```python
class JsonFieldTracker:
    state: str  # "awaiting_key" | "in_string" | "after_comma" …
    current_field: str | None
    tokens_in_field: dict[str, int]
```

### 3. Cut-and-restart sur dépassement de budget

Quand `tokens_in_field["thinking"] > settings["thinkingTokens"]` :
1. **Abort** la requête httpx en cours (`task.cancel()` + fermer le stream)
2. **Construire un prefix** : ce qu'on a déjà reçu + clôture forcée du champ
   `thinking` → par exemple `{"thinking": "...[truncated]...", "narrative": "`
3. **Second appel** llama-server avec :
   - `cache_prompt: true` → réutilise le KV cache du prompt système (pas de
     recomputation)
   - `prompt` = messages + prefill du JSON partiel
   - Grammaire qui reprend depuis le champ courant
4. **Concaténer** les deux streams côté client

Même logique pour `narrative` → `suggestions` si on veut être strict sur les
trois budgets.

### 4. Relay SSE vers le frontend

FastAPI supporte `StreamingResponse` avec `media_type="text/event-stream"`.
- Route `GET /api/sessions/{id}/generate/stream` qui retourne un SSE
- Chaque event contient `{type: "token" | "field_start" | "done" | "error",
  data: ...}`
- Frontend consomme via `EventSource` natif ou `ky` + parser

Alternative : WebSocket bidirectionnel (FastAPI Supports natif). Plus flexible
pour de l'interrupt côté user ("Stop generation" button) mais plus de boilerplate.

### 5. Frontend Vue

- Store action `generateStreaming(sessionId, directive)` qui ouvre l'EventSource
- State réactif : buffer de tokens pour chaque champ
- `NarrativeDisplay.vue` lit le buffer → re-render au fur et à mesure
- `ThinkingPanel.vue` affiche les tokens du champ `thinking` en live
- Affichage de stop/cancel propre

## Complications à anticiper

- **Grammaire + prefill** : GBNF doit pouvoir reprendre depuis un JSON partiel
  valide. À tester avec llama.cpp, peut nécessiter d'adapter la grammaire ou
  d'utiliser `grammar_lazy` pour autoriser des prefix hors-grammar.
- **Tokens vs caractères** : llama-server envoie des deltas texte, pas des
  tokens. Le comptage "tokens dans le champ" doit passer par `usage` (envoyé
  dans le dernier chunk) ou par une approximation (ratio char/token du modèle).
  Sinon `stream=True&include_usage=true` côté OpenAI-compat donne le compteur.
- **Cancellation propre** : fermer le stream httpx sans laisser le slot de
  llama-server en état bancal. Tester que le slot redevient `is_processing:
  false` rapidement après abort.
- **Activity view** : instrumenter le nouveau flow dans `llm_activity.py`. Un
  call = potentiellement plusieurs sous-requêtes llama-server (cut-restart) →
  choisir si on log chacune ou si on agrège.

## Ordre d'implémentation suggéré

1. **MVP stream sans cut** : câbler `generate_completion_stream`, relay SSE
   vers le frontend pour la narration seule. Vérifier que ça marche avec la
   grammaire.
2. **Cut-and-restart** : ajouter le tracker + la logique de restart.
3. **Les 3 budgets** : étendre aux champs `narrative` et `suggestions`.
4. **Utility calls** (title, meta, chub, consolidate) : décider si on les
   passe aussi en stream ou si on les laisse en bloquant (utile pour debug
   mais pas critique UX).

## Estimation

~3-4h bien fait, en sessions dédiées. Le gros morceau est le parser JSON
incrémental robuste + les tests de bout-en-bout avec différents modèles
(reasoning vs non-reasoning). Le relay SSE et le frontend sont triviaux une
fois le backend stable.

## Hors scope (backlog du backlog)

- WebSocket pour une UX avec bouton Stop/Regen à chaud
- Multi-slot : utiliser plusieurs slots llama-server en parallèle pour des
  utility calls concurrents (title + meta + narrative sur 3 slots du même
  modèle)
- Streaming des utility calls vers l'Activity view (voir le chub-import se
  construire en live)
