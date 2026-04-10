<template>
  <div class="session-view">
    <aside class="sidebar">
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

    <div class="main-area">
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

    <div v-if="narrativeStore.error" class="error-toast" @click="narrativeStore.error = null">
      {{ narrativeStore.error }}
    </div>
  </div>
</template>

<script setup>
import { onMounted, watch } from 'vue';
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
}

async function createChapter() {
  const title = window.prompt('Chapter title:');
  if (!title) return;
  try {
    const chapter = await api.post(`sessions/${sessionId}/chapters`, { json: { title } }).json();
    sessionStore.currentSession.chapters.push(chapter);
    narrativeStore.setChapters(sessionStore.currentSession.chapters);
    await narrativeStore.loadChapter(sessionId, chapter.id);
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
.session-view {
  display: flex;
  height: calc(100vh - 49px);
  position: relative;
}

.sidebar {
  width: 260px;
  min-width: 260px;
  background: var(--color-bg-secondary);
  border-right: 1px solid var(--color-border);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.error-toast {
  position: fixed;
  bottom: 5rem;
  left: 50%;
  transform: translateX(-50%);
  background: #c0392b;
  color: white;
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  font-size: 0.9rem;
  cursor: pointer;
  z-index: 50;
  max-width: 600px;
}
</style>
