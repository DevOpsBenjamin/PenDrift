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
      <ChapterList
        :chapters="sessionStore.currentSession?.chapters || []"
        :currentChapterId="narrativeStore.currentChapterId"
        @select="switchChapter"
        @create="createChapter"
      />
      <CharacterPanel
        :characters="narrativeStore.characters"
        :updating="narrativeStore.characterUpdatePending"
      />
    </aside>

    <!-- Main content -->
    <div class="flex-1 flex flex-col min-w-0">
      <NarrativeDisplay
        :chunks="narrativeStore.currentChapterChunks"
        :generating="narrativeStore.generating"
        @regenerate="handleRegenerate"
        @delete="handleDelete"
      />
      <DirectiveInput
        :generating="narrativeStore.generating"
        @submit="handleGenerate"
      />
    </div>

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
import { ref, onMounted, onUnmounted } from 'vue';
import { useRoute } from 'vue-router';
import { useSessionStore } from '../stores/session.js';
import { useNarrativeStore } from '../stores/narrative.js';
import ChapterList from '../components/chapters/ChapterList.vue';
import CharacterPanel from '../components/characters/CharacterPanel.vue';
import NarrativeDisplay from '../components/narrative/NarrativeDisplay.vue';
import DirectiveInput from '../components/narrative/DirectiveInput.vue';
import api from '../api/client.js';

const route = useRoute();
const sessionStore = useSessionStore();
const narrativeStore = useNarrativeStore();

const sessionId = route.params.id;
const sidebarOpen = ref(false);

onMounted(async () => {
  await sessionStore.loadSession(sessionId);
  if (sessionStore.currentSession) {
    narrativeStore.setChapters(sessionStore.currentSession.chapters);
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

async function createChapter() {
  const title = window.prompt('Chapter title:');
  if (!title) return;
  try {
    const chapter = await api.post(`sessions/${sessionId}/chapters`, { json: { title } }).json();
    sessionStore.currentSession.chapters.push(chapter);
    narrativeStore.setChapters(sessionStore.currentSession.chapters);
    await narrativeStore.loadChapter(sessionId, chapter.id);
    sidebarOpen.value = false;
  } catch (err) {
    narrativeStore.error = err.message;
  }
}

async function handleGenerate({ directive, isKeyMoment }) {
  await narrativeStore.generate(sessionId, directive, isKeyMoment);
}

async function handleRegenerate() {
  await narrativeStore.regenerateLast(sessionId);
}

async function handleDelete() {
  if (window.confirm('Delete the last generated chunk?')) {
    await narrativeStore.deleteLastChunk(sessionId);
  }
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
