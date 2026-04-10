/**
 * Replaces all {{variable}} placeholders using the template's variables map.
 */
function resolveVariables(text, variables) {
  if (!text || !variables) return text;
  return text.replace(/\{\{(\w+)\}\}/g, (match, key) => {
    return variables[key] !== undefined ? variables[key] : match;
  });
}

/**
 * Builds the messages array for an LLM generation call.
 * Only sends the last N chunks (recentChunksCount), not the full history.
 */
export function buildMessages({ settings, characters, template, chunks, directive, importantFacts }) {
  const messages = [];
  const vars = template?.variables || {};
  const resolve = (text) => resolveVariables(text, vars);

  // 1. System prompt: narrative prompt + scenario + style + intents + characters + facts
  let system = settings.narrativePrompt || settings.systemPrompt || '';

  // Scenario context
  if (template?.scenario) {
    system += `\n\n## Scenario\n${resolve(template.scenario)}`;
  }

  // Template-specific additions
  if (template?.systemPromptAdditions) {
    system += `\n\n## Style Instructions\n${resolve(template.systemPromptAdditions)}`;
  }

  // Masked intents (hidden narrative drivers)
  if (template?.maskedIntents?.length) {
    system += '\n\n## Hidden Narrative Drivers (never reveal these directly)\n';
    system += template.maskedIntents.map(i => `- ${resolve(i)}`).join('\n');
  }

  // Current character sheets
  if (characters?.length) {
    system += '\n\n## Current Character States\n';
    for (const char of characters) {
      system += `\n### ${char.name}\n`;
      system += `State: ${char.currentState}\n`;
      if (char.traits?.length) {
        system += `Traits: ${char.traits.join(', ')}\n`;
      }
      if (char.keyEvents?.length) {
        system += `Key events: ${char.keyEvents.join('; ')}\n`;
      }
    }
  }

  // Important facts from meta-calls
  if (importantFacts?.length) {
    system += '\n\n## Established Facts\n';
    system += importantFacts.map(f => `- ${f}`).join('\n');
  }

  messages.push({ role: 'system', content: system });

  // 2. Recent narrative chunks only (not full history)
  const recentCount = settings.recentChunksCount || 20;
  const recentChunks = chunks?.slice(-recentCount) || [];

  if (recentChunks.length) {
    const narrativeHistory = recentChunks.map(c => c.narrative).join('\n\n');
    messages.push({ role: 'assistant', content: narrativeHistory });
  }

  // 3. Current directive as user message
  messages.push({ role: 'user', content: directive });

  return messages;
}

/**
 * Builds the messages array for the enriched meta-call.
 * Analyzes recent narrative and returns character updates, new characters,
 * consistency flags, and important facts.
 */
export function buildMetaAnalysisMessages({ characters, recentChunks, importantFacts, metaPrompt }) {
  const narrativeText = recentChunks.map(c => c.narrative).join('\n\n');

  const system = metaPrompt || `You are a narrative analyst. Analyze recent narrative events and maintain story consistency.

Your tasks:
1. UPDATE existing character sheets to reflect how they have evolved
2. DETECT any new characters mentioned in the narrative and create sheets for them
3. FLAG any consistency issues (name changes, contradictions, forgotten facts)
4. EXTRACT important facts established in the narrative (locations, relationships, promises, secrets)

Return ONLY valid JSON in this exact format, no other text:
{
  "characterUpdates": [
    { "name": "Character Name", "currentState": "updated state", "traits": ["trait1"], "keyEvents": ["event1"] }
  ],
  "newCharacters": [
    { "name": "New Char", "currentState": "state", "traits": [], "keyEvents": ["first mentioned context"] }
  ],
  "consistencyFlags": ["any inconsistencies found"],
  "importantFacts": ["key facts established in the narrative"]
}`;

  let userContent = `## Current Character Sheets\n${JSON.stringify(characters, null, 2)}`;

  if (importantFacts?.length) {
    userContent += `\n\n## Previously Established Facts\n${importantFacts.map(f => `- ${f}`).join('\n')}`;
  }

  userContent += `\n\n## Recent Narrative\n${narrativeText}`;
  userContent += '\n\nAnalyze the narrative above. Return only the JSON object.';

  return [
    { role: 'system', content: system },
    { role: 'user', content: userContent },
  ];
}
