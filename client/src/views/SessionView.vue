<template>
  <div class="flex flex-1 h-[calc(100dvh-49px)] relative overflow-hidden">
    <!-- Mobile sidebar toggle -->
    <button
      class="md:hidden fixed bottom-20 left-3 z-30 w-10 h-10 bg-bg-elevated border border-border rounded-full
             flex items-center justify-center text-text-secondary hover:text-text-primary shadow-lg transition-all"
      @click="sidebarOpen = !sidebarOpen"
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h8m-8 6h16" />
      </svg>
    </button>

    <!-- Sidebar overlay (mobile) -->
    <Transition name="fade">
      <div
        v-if="sidebarOpen"
        class="md:hidden fixed inset-0 bg-bg-overlay z-30"
        @click="sidebarOpen = false"
      ></div>
    </Transition>

    <!-- Sidebar -->
    <aside
      class="fixed md:relative z-40 md:z-auto h-full w-72 md:w-60 bg-bg-secondary border-r border-border-subtle
             flex flex-col overflow-y-auto transition-transform duration-300 ease-out
             md:translate-x-0"
      :class="sidebarOpen ? 'translate-x-0' : '-translate-x-full'"
    >
      <div class="px-3 pt-3 pb-2 flex flex-col gap-2">
        <h2 class="text-sm font-semibold text-text-primary truncate">{{ sessionStore.currentSession?.title }}</h2>
        <div class="flex items-center gap-2">
          <label class="text-xs text-text-muted shrink-0">Preset:</label>
          <select
            :value="sessionStore.currentSession?.settingsPresetId || 'default'"
            @change="sessionStore.updateCurrentPreset($event.target.value)"
            class="flex-1 min-w-0 px-2 py-1 bg-bg-primary border border-border rounded text-xs text-text-secondary
                   focus:outline-none focus:border-accent transition-colors cursor-pointer"
          >
            <option v-for="p in settingsStore.presets" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>
        <div v-if="templateVersions.length > 1" class="flex items-center gap-2">
          <label class="text-xs text-text-muted shrink-0" title="Pin this session to a specific template version. Changing the template later won't affect this session unless you switch here.">Tpl ver:</label>
          <select
            :value="sessionStore.currentSession?.templateVersion || ''"
            @change="changeTemplateVersion($event.target.value)"
            class="flex-1 min-w-0 px-2 py-1 bg-bg-primary border border-border rounded text-xs text-text-secondary
                   focus:outline-none focus:border-accent transition-colors cursor-pointer"
          >
            <option v-for="v in templateVersions" :key="v.version" :value="v.version">
              {{ v.version }} · {{ v.action }}
            </option>
          </select>
        </div>
      </div>
      <ChapterList
        :chapters="sessionStore.currentSession?.chapters || []"
        :currentChapterId="narrativeStore.currentChapterId"
        :finalizing="finalizing"
        :sessionFinished="!!sessionStore.currentSession?.finishedAt"
        :finishing="finishing"
        :validating="validating"
        :reopening="reopening"
        @select="switchChapter"
        @rename="renameChapter"
        @finalize="finalizeChapter"
        @regenTitle="regenTitle"
        @finish="finishSession"
        @validateFinish="validateFinish"
        @reopen="reopenFinished"
      />
      <!-- Initial-meta status banner: shows while the background job is
           extracting structured character state from the template. Once
           status flips to 'done' or 'failed', this disappears (and characters
           are auto-reloaded by the watcher in script). -->
      <div
        v-if="initialMetaPending"
        class="mx-3 mt-2 p-2.5 rounded-lg border border-accent/40 bg-accent/5 flex items-start gap-2 text-[11px] text-text-secondary"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 text-accent shrink-0 mt-0.5 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h5M20 20v-5h-5M4 9a8 8 0 0114-4M20 15a8 8 0 01-14 4" />
        </svg>
        <span class="leading-relaxed">Setting up character context… you can start writing already; richer data will load when ready.</span>
      </div>
      <div
        v-else-if="initialMetaFailed"
        class="mx-3 mt-2 p-2.5 rounded-lg border border-warning/40 bg-warning/5 text-[11px] text-text-secondary leading-relaxed"
      >
        Initial character extraction failed — the session will run on legacy template seeding. Check provider settings and recreate if needed.
      </div>
      <CharacterPanel
        :characters="narrativeStore.characters"
        :updating="narrativeStore.metaUpdatePending"
        :flags="narrativeStore.consistencyFlags"
        @saveCharacter="handleSaveCharacter"
        @editFacts="openFactsEditor"
      />
      <div class="p-3 border-t border-border-subtle space-y-1">
        <button
          class="w-full py-2 text-xs text-text-muted hover:text-text-secondary hover:bg-bg-surface/50
                 rounded-lg transition-all cursor-pointer flex items-center justify-center gap-1.5 relative"
          @click="showAskNarrator = true"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.008v.008H12V17z M12 21a9 9 0 110-18 9 9 0 010 18z" />
          </svg>
          Ask the Narrator
          <span
            v-if="pendingNarratorAnswer"
            class="ml-1 inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-mono uppercase tracking-wider bg-accent/20 text-accent border border-accent/40 animate-pulse"
            title="A new answer arrived while the modal was closed."
          >New</span>
        </button>
        <button
          class="w-full py-2 text-xs text-purple-300/70 hover:text-purple-200 hover:bg-purple-500/10
                 rounded-lg transition-all cursor-pointer flex items-center justify-center gap-1.5 relative"
          title="Meta-analyst on the template — diagnose what's coded, missing, or causing the story to stall. Session attached as evidence."
          @click="showAskTemplate = true"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
          </svg>
          Ask the Template
          <span
            v-if="pendingTemplateAnswer"
            class="ml-1 inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-mono uppercase tracking-wider bg-purple-500/20 text-purple-300 border border-purple-400/40 animate-pulse"
            title="A new answer arrived while the modal was closed."
          >New</span>
        </button>
        <button
          class="w-full py-2 text-xs text-purple-300/70 hover:text-purple-200 hover:bg-purple-500/10
                 rounded-lg transition-all cursor-pointer flex items-center justify-center gap-1.5"
          title="Rewrite the template using your feedback and selected diagnostic asks. Lands as a new version on disk; existing sessions stay pinned."
          @click="showRewriteTemplate = true"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
          </svg>
          Rewrite Template
        </button>
        <button
          class="w-full py-2 text-xs text-text-muted hover:text-text-secondary hover:bg-bg-surface/50
                 rounded-lg transition-all cursor-pointer"
          @click="openMetaHistory"
        >Meta-Analysis History</button>
      </div>
    </aside>

    <!-- Main content — h-full forces fixed height, no page scroll -->
    <div class="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
      <NarrativeDisplay
        :chunks="narrativeStore.currentChapterChunks"
        :generating="narrativeStore.generating"
        :finalized="currentChapterFinalized || sessionFinished"
        @regenerate="handleRegenerate"
        @delete="handleDelete"
        @edit="handleEdit"
        @switchVersion="handleSwitchVersion"
      />
      <DirectiveInput
        :generating="narrativeStore.generating"
        :finalized="currentChapterFinalized || sessionFinished"
        @submit="handleGenerate"
      />
    </div>

    <!-- Facts Editor -->
    <FactsEditor
      v-if="showFactsEditor"
      :facts="facts"
      @close="showFactsEditor = false"
      @save="handleSaveFacts"
    />

    <!-- Meta History Modal -->
    <MetaHistoryPanel
      v-if="showMetaHistory"
      :history="narrativeStore.metaHistory"
      @close="showMetaHistory = false"
      @retryMeta="handleRetryMeta"
      @consolidateMeta="handleConsolidateMeta"
    />

    <!-- Ask the Narrator Modal -->
    <AskNarratorModal
      v-if="showAskNarrator"
      @close="showAskNarrator = false"
    />

    <!-- Ask the Template Modal -->
    <AskTemplateModal
      v-if="showAskTemplate && sessionStore.currentSession?.templateId"
      :templateId="sessionStore.currentSession.templateId"
      :sessionId="sessionId"
      @close="showAskTemplate = false"
    />

    <!-- Rewrite Template Modal -->
    <RewriteTemplateModal
      v-if="showRewriteTemplate && sessionStore.currentSession?.templateId"
      :templateId="sessionStore.currentSession.templateId"
      :currentVersion="sessionStore.currentSession?.templateVersion"
      @close="showRewriteTemplate = false"
      @done="onRewriteDone"
    />

    <!-- Error toast -->
    <Transition name="toast">
      <div
        v-if="narrativeStore.error"
        class="fixed bottom-24 left-1/2 -translate-x-1/2 z-50 bg-error text-white px-5 py-3 rounded-xl
               text-sm shadow-lg shadow-error/20 cursor-pointer max-w-lg"
        @click="narrativeStore.error = null"
      >
        {{ narrativeStore.error }}
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { useRoute } from 'vue-router';
import { useSessionStore } from '../stores/session.js';
import { useNarrativeStore } from '../stores/narrative.js';
import { useSettingsStore } from '../stores/settings.js';
import { useJobsStore } from '../stores/jobs.js';
import ChapterList from '../components/chapters/ChapterList.vue';
import CharacterPanel from '../components/characters/CharacterPanel.vue';
import MetaHistoryPanel from '../components/characters/MetaHistoryPanel.vue';
import FactsEditor from '../components/characters/FactsEditor.vue';
import NarrativeDisplay from '../components/narrative/NarrativeDisplay.vue';
import DirectiveInput from '../components/narrative/DirectiveInput.vue';
import AskNarratorModal from '../components/narrative/AskNarratorModal.vue';
import AskTemplateModal from '../components/templates/AskTemplateModal.vue';
import RewriteTemplateModal from '../components/templates/RewriteTemplateModal.vue';
import * as charactersApi from '../api/characters.js';
import * as generateApi from '../api/generate.js';
import * as templatesApi from '../api/templates.js';
import * as sessionsApi from '../api/sessions.js';
import api from '../api/client.js';

const route = useRoute();
const sessionStore = useSessionStore();
const narrativeStore = useNarrativeStore();
const settingsStore = useSettingsStore();
const jobsStore = useJobsStore();

const sessionId = route.params.id;
const sidebarOpen = ref(false);
const showMetaHistory = ref(false);
const showFactsEditor = ref(false);
const showAskNarrator = ref(false);
const showAskTemplate = ref(false);
const showRewriteTemplate = ref(false);

// Notification flags — set when an Ask job finishes WHILE its modal is closed
// (so the user knows a fresh answer is waiting). Cleared when the modal opens.
const pendingNarratorAnswer = ref(false);
const pendingTemplateAnswer = ref(false);

async function onRewriteDone(payload) {
  // Two cases:
  // - { started: true } : modal was submitted, rewrite job is running in
  //   background. The toast bar in the header shows progress; we'll refresh
  //   the version selector once the job is observed as complete (watcher
  //   below). No user-facing toast yet — the running toast is the toast.
  // - { version: "0002" } : legacy path if the modal ever streams to
  //   completion locally. Refresh immediately and announce the version.
  if (payload?.version) {
    await loadTemplateVersions();
    narrativeStore.error = `New template version ${payload.version} saved. Switch to it via the "Tpl ver" selector if you want this session to use it.`;
  }
  // For `started`: the watcher below handles the refresh on completion.
}

// When a template-rewrite job for this session's template finishes, refresh
// the version selector so the new version becomes pickable. Watching the
// jobs store is cheaper than polling, since the store is already SSE-fed.
watch(
  () => jobsStore.byKind('template-rewrite').filter(j => j.status === 'done').length,
  async (newCount, oldCount) => {
    if (oldCount != null && newCount > oldCount) {
      await loadTemplateVersions();
    }
  },
);

// Notification badges — set the pending flag when an ask job for this
// session/template completes WHILE the corresponding modal is closed. The
// flag is cleared when the user opens the modal (the watcher below).
watch(
  () => jobsStore.byKind('query')
    .filter(j => j.sessionId === sessionId && j.status === 'done').length,
  (newCount, oldCount) => {
    if (oldCount != null && newCount > oldCount && !showAskNarrator.value) {
      pendingNarratorAnswer.value = true;
    }
  },
);
watch(
  () => jobsStore.byKind('template-query').filter(j => j.status === 'done').length,
  (newCount, oldCount) => {
    if (oldCount != null && newCount > oldCount && !showAskTemplate.value) {
      pendingTemplateAnswer.value = true;
    }
  },
);
watch(showAskNarrator, (open) => { if (open) pendingNarratorAnswer.value = false; });
watch(showAskTemplate, (open) => { if (open) pendingTemplateAnswer.value = false; });
const facts = ref([]);
const finalizing = ref(false);
const finishing = ref(false);
const validating = ref(false);
const reopening = ref(false);
const templateVersions = ref([]);

async function loadTemplateVersions() {
  const tid = sessionStore.currentSession?.templateId;
  if (!tid) {
    templateVersions.value = [];
    return;
  }
  try {
    templateVersions.value = await templatesApi.listTemplateVersions(tid);
  } catch {
    templateVersions.value = [];
  }
}

async function changeTemplateVersion(version) {
  await sessionStore.updateCurrentTemplateVersion(version);
}

const currentChapterFinalized = computed(() => {
  const ch = sessionStore.currentSession?.chapters?.find(c => c.id === narrativeStore.currentChapterId);
  return ch?.finalized || false;
});
const sessionFinished = computed(() => !!sessionStore.currentSession?.finishedAt);

const initialMetaStatus = computed(() => sessionStore.currentSession?.initialMetaStatus || 'done');
const initialMetaPending = computed(() => initialMetaStatus.value === 'pending' || initialMetaStatus.value === 'running');
const initialMetaFailed = computed(() => initialMetaStatus.value === 'failed');

// Poll the session every 3s while initial-meta is in flight. When it finishes
// (status flips to 'done' or 'failed'), we stop polling and reload characters
// so the structured fields the background job populated become visible.
let initialMetaPollHandle = null;
function startInitialMetaPolling() {
  if (initialMetaPollHandle) return;
  initialMetaPollHandle = setInterval(() => {
    sessionStore.loadSession(sessionId);
  }, 3000);
}
function stopInitialMetaPolling() {
  if (initialMetaPollHandle) {
    clearInterval(initialMetaPollHandle);
    initialMetaPollHandle = null;
  }
}
watch(initialMetaStatus, (status, prev) => {
  if (status === 'pending' || status === 'running') {
    startInitialMetaPolling();
  } else {
    stopInitialMetaPolling();
    if (prev === 'pending' || prev === 'running') {
      // Just finished — reload characters so the new structured fields show up.
      narrativeStore.loadCharacters(sessionId);
    }
  }
}, { immediate: true });

onUnmounted(stopInitialMetaPolling);


async function openMetaHistory() {
  // Fetch BEFORE opening so the modal mounts with the data ready —
  // avoids the "first click shows empty" race.
  await narrativeStore.loadMetaHistory(sessionId);
  showMetaHistory.value = true;
}

async function openFactsEditor() {
  try {
    facts.value = await api.get(`sessions/${sessionId}/facts`).json();
  } catch { /* ignore, modal will show whatever was loaded last */ }
  showFactsEditor.value = true;
}

onMounted(async () => {
  await sessionStore.loadSession(sessionId);
  if (!settingsStore.presets.length) settingsStore.fetchPresets();
  if (sessionStore.currentSession) {
    narrativeStore.setChapters(sessionId, sessionStore.currentSession.chapters);
    if (narrativeStore.currentChapterId) {
      await narrativeStore.loadChapter(sessionId, narrativeStore.currentChapterId);
    }
    await narrativeStore.loadCharacters(sessionId);
    narrativeStore.loadMetaHistory(sessionId);
    // If a generation is already in flight (e.g. user refreshed the page
    // while it was running), re-attach the live stream UI to it.
    narrativeStore.tryAttachStream(sessionId);
    loadTemplateVersions();
  }
});

async function switchChapter(chapterId) {
  await narrativeStore.loadChapter(sessionId, chapterId);
  sidebarOpen.value = false;
}

async function finalizeChapter() {
  if (!narrativeStore.currentChapterId) return;
  finalizing.value = true;
  try {
    const result = await api.post(`sessions/${sessionId}/chapters/finalize`, {
      json: { chapterId: narrativeStore.currentChapterId },
      timeout: 600000,
    }).json();

    // Update session chapters
    const idx = sessionStore.currentSession.chapters.findIndex(c => c.id === result.finalizedChapter.id);
    if (idx >= 0) {
      sessionStore.currentSession.chapters[idx] = result.finalizedChapter;
    }
    sessionStore.currentSession.chapters.push(result.newChapter);
    narrativeStore.setChapters(sessionId, sessionStore.currentSession.chapters);

    // Switch to new chapter
    await narrativeStore.loadChapter(sessionId, result.newChapter.id);
    await narrativeStore.loadCharacters(sessionId);
    sidebarOpen.value = false;
  } catch (err) {
    narrativeStore.error = err.message;
  } finally {
    finalizing.value = false;
  }
}

async function finishSession() {
  if (finishing.value) return;
  const ok = window.confirm(
    "Generate the epilogue?\n\n" +
    "This produces a 10-14 paragraph closing scene with a deliberate time jump " +
    "that resolves each character's arc. The session is NOT yet locked — review " +
    "the chunk after generation, regenerate if you want, and click Validate & Lock " +
    "when satisfied."
  );
  if (!ok) return;
  finishing.value = true;
  try {
    await sessionsApi.streamFinish(sessionId, (ev) => {
      if (ev.type === 'error') {
        narrativeStore.error = ev.message || 'Epilogue generation failed';
      }
    });
    // Refresh session (new Epilogue chapter or renamed trailing) and load it.
    await sessionStore.loadSession(sessionId);
    if (sessionStore.currentSession) {
      narrativeStore.setChapters(sessionId, sessionStore.currentSession.chapters);
      const chapters = sessionStore.currentSession.chapters;
      const epilogue = chapters[chapters.length - 1];
      if (epilogue) {
        await narrativeStore.loadChapter(sessionId, epilogue.id);
      }
      await narrativeStore.loadCharacters(sessionId);
    }
  } catch (err) {
    narrativeStore.error = err.message;
  } finally {
    finishing.value = false;
  }
}

async function validateFinish() {
  if (validating.value) return;
  const ok = window.confirm(
    "Lock this session as finished?\n\n" +
    "The currently-active version of every chunk becomes THE version — version " +
    "switching is disabled in finished mode. You can reopen the session later " +
    "if you want to keep writing."
  );
  if (!ok) return;
  validating.value = true;
  try {
    const updated = await sessionsApi.validateFinish(sessionId);
    sessionStore.currentSession = updated;
    const idx = sessionStore.sessions.findIndex(s => s.id === sessionId);
    if (idx >= 0) sessionStore.sessions[idx] = updated;
  } catch (err) {
    narrativeStore.error = err.message;
  } finally {
    validating.value = false;
  }
}

async function reopenFinished() {
  if (reopening.value) return;
  reopening.value = true;
  try {
    const updated = await sessionsApi.reopenFinished(sessionId);
    sessionStore.currentSession = updated;
    const idx = sessionStore.sessions.findIndex(s => s.id === sessionId);
    if (idx >= 0) sessionStore.sessions[idx] = updated;
  } catch (err) {
    narrativeStore.error = err.message;
  } finally {
    reopening.value = false;
  }
}

async function regenTitle(chapterId) {
  try {
    const result = await api.post(`sessions/${sessionId}/chapters/${chapterId}/regen-title`, { timeout: 600000 }).json();
    const chapter = sessionStore.currentSession.chapters.find(c => c.id === chapterId);
    if (chapter) chapter.title = result.title;
  } catch (err) {
    narrativeStore.error = err.message;
  }
}

async function renameChapter({ chapterId, title }) {
  try {
    await api.put(`sessions/${sessionId}/chapters/${chapterId}`, { json: { title } }).json();
    const chapter = sessionStore.currentSession.chapters.find(c => c.id === chapterId);
    if (chapter) chapter.title = title;
  } catch (err) {
    narrativeStore.error = err.message;
  }
}

async function handleGenerate({ directive, isKeyMoment }) {
  await narrativeStore.generate(sessionId, directive, isKeyMoment);
}

async function handleRegenerate({ chunkId, directive }) {
  await narrativeStore.regenerateChunk(sessionId, chunkId, directive);
}

async function handleEdit({ chunkId, narrative }) {
  try {
    const updated = await api.put(`sessions/${sessionId}/chunks/${chunkId}`, { json: { narrative } }).json();
    const chunk = narrativeStore.chunks.find(c => c.id === chunkId);
    if (chunk) {
      chunk.versions = updated.versions;
      chunk.activeVersion = updated.activeVersion;
    }
  } catch (err) {
    narrativeStore.error = err.message;
  }
}

function handleSwitchVersion({ chunkId, versionIndex }) {
  // Instant client-side switch — no API call, persisted on next save/generate
  const chunk = narrativeStore.chunks.find(c => c.id === chunkId);
  if (chunk) {
    chunk.activeVersion = versionIndex;
    // Lazy persist in background, don't block UI
    generateApi.setChunkVersion(sessionId, chunkId, versionIndex).catch(() => {});
  }
}

async function handleRetryMeta() {
  try {
    narrativeStore.metaUpdatePending = true;
    await api.post(`sessions/${sessionId}/characters/update`, {
      json: { chapterId: narrativeStore.currentChapterId },
      timeout: 600000,
    }).json();
    await narrativeStore.loadCharacters(sessionId);
    await narrativeStore.loadMetaHistory(sessionId);
  } catch (err) {
    narrativeStore.error = err.message;
  } finally {
    narrativeStore.metaUpdatePending = false;
  }
}

async function handleConsolidateMeta() {
  try {
    narrativeStore.metaUpdatePending = true;
    await api.post(`sessions/${sessionId}/characters/consolidate`, {
      timeout: 600000,
    }).json();
    await narrativeStore.loadCharacters(sessionId);
    await narrativeStore.loadMetaHistory(sessionId);
  } catch (err) {
    narrativeStore.error = err.message;
  } finally {
    narrativeStore.metaUpdatePending = false;
  }
}

async function handleSaveCharacter(char) {
  try {
    if (char._isNew) {
      delete char._isNew;
      await api.post(`sessions/${sessionId}/characters`, { json: char }).json();
    } else {
      await api.put(`sessions/${sessionId}/characters/${encodeURIComponent(char.name)}`, { json: char }).json();
    }
    await narrativeStore.loadCharacters(sessionId);
  } catch (err) {
    narrativeStore.error = err.message;
  }
}

async function handleSaveFacts(newFacts) {
  try {
    await api.put(`sessions/${sessionId}/facts`, { json: { facts: newFacts } }).json();
    facts.value = newFacts;
    showFactsEditor.value = false;
  } catch (err) {
    narrativeStore.error = err.message;
  }
}

async function handleDelete(chunkId) {
  await narrativeStore.deleteVersion(sessionId, chunkId);
}
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.toast-enter-active {
  transition: all 0.3s var(--ease-spring);
}
.toast-leave-active {
  transition: all 0.2s ease;
}
.toast-enter-from {
  transform: translateX(-50%) translateY(20px);
  opacity: 0;
}
.toast-leave-to {
  transform: translateX(-50%) translateY(-10px);
  opacity: 0;
}
</style>
