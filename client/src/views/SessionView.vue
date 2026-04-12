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
      <div class="px-3 pt-3 pb-1">
        <h2 class="text-sm font-semibold text-text-primary truncate">{{ sessionStore.currentSession?.title }}</h2>
      </div>
      <ChapterList
        :chapters="sessionStore.currentSession?.chapters || []"
        :currentChapterId="narrativeStore.currentChapterId"
        :finalizing="finalizing"
        @select="switchChapter"
        @rename="renameChapter"
        @finalize="finalizeChapter"
        @regenTitle="regenTitle"
      />
      <CharacterPanel
        :characters="narrativeStore.characters"
        :updating="narrativeStore.metaUpdatePending"
        :flags="narrativeStore.consistencyFlags"
        @saveCharacter="handleSaveCharacter"
        @editFacts="showFactsEditor = true"
      />
      <div class="p-3 border-t border-border-subtle">
        <button
          class="w-full py-2 text-xs text-text-muted hover:text-text-secondary hover:bg-bg-surface/50
                 rounded-lg transition-all cursor-pointer"
          @click="showMetaHistory = true"
        >Meta-Analysis History</button>
      </div>
    </aside>

    <!-- Main content — h-full forces fixed height, no page scroll -->
    <div class="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
      <NarrativeDisplay
        :chunks="narrativeStore.currentChapterChunks"
        :generating="narrativeStore.generating"
        :finalized="currentChapterFinalized"
        @regenerate="handleRegenerate"
        @delete="handleDelete"
        @edit="handleEdit"
        @switchVersion="handleSwitchVersion"
      />
      <DirectiveInput
        :generating="narrativeStore.generating"
        :finalized="currentChapterFinalized"
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
      :history="metaHistory"
      @close="showMetaHistory = false"
      @retryMeta="handleRetryMeta"
      @consolidateMeta="handleConsolidateMeta"
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
import { ref, computed, watch, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { useSessionStore } from '../stores/session.js';
import { useNarrativeStore } from '../stores/narrative.js';
import ChapterList from '../components/chapters/ChapterList.vue';
import CharacterPanel from '../components/characters/CharacterPanel.vue';
import MetaHistoryPanel from '../components/characters/MetaHistoryPanel.vue';
import FactsEditor from '../components/characters/FactsEditor.vue';
import NarrativeDisplay from '../components/narrative/NarrativeDisplay.vue';
import DirectiveInput from '../components/narrative/DirectiveInput.vue';
import * as charactersApi from '../api/characters.js';
import * as generateApi from '../api/generate.js';
import api from '../api/client.js';

const route = useRoute();
const sessionStore = useSessionStore();
const narrativeStore = useNarrativeStore();

const sessionId = route.params.id;
const sidebarOpen = ref(false);
const showMetaHistory = ref(false);
const metaHistory = ref([]);
const showFactsEditor = ref(false);
const facts = ref([]);
const finalizing = ref(false);

const currentChapterFinalized = computed(() => {
  const ch = sessionStore.currentSession?.chapters?.find(c => c.id === narrativeStore.currentChapterId);
  return ch?.finalized || false;
});


watch(showMetaHistory, async (open) => {
  if (open) {
    metaHistory.value = await charactersApi.getMetaHistory(sessionId);
  }
});

watch(showFactsEditor, async (open) => {
  if (open) {
    facts.value = await api.get(`sessions/${sessionId}/facts`).json();
  }
});

onMounted(async () => {
  await sessionStore.loadSession(sessionId);
  if (sessionStore.currentSession) {
    narrativeStore.setChapters(sessionId, sessionStore.currentSession.chapters);
    if (narrativeStore.currentChapterId) {
      await narrativeStore.loadChapter(sessionId, narrativeStore.currentChapterId);
    }
    await narrativeStore.loadCharacters(sessionId);
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
    metaHistory.value = await charactersApi.getMetaHistory(sessionId);
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
    metaHistory.value = await charactersApi.getMetaHistory(sessionId);
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
