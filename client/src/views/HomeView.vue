<template>
  <div class="home flex-1">
    <main class="max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
      <div class="flex items-center justify-between mb-6 sm:mb-8">
        <h1 class="font-body text-2xl sm:text-3xl font-bold">Sessions</h1>
        <button
          class="px-4 py-2.5 bg-accent rounded-lg text-white text-sm font-semibold cursor-pointer
                 hover:bg-accent-hover transition-colors active:scale-95"
          @click="showCreateModal = true"
        >+ New Session</button>
      </div>

      <div v-if="store.loading" class="text-center text-text-secondary py-16">
        <div class="inline-block w-6 h-6 border-2 border-accent/30 border-t-accent rounded-full animate-spin"></div>
      </div>

      <div v-else-if="store.sessions.length === 0" class="text-center text-text-secondary py-20 space-y-2">
        <p class="text-lg">No sessions yet</p>
        <p class="text-sm text-text-muted">Create one to start writing.</p>
      </div>

      <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <SessionCard
          v-for="session in store.sessions"
          :key="session.id"
          :session="session"
          @select="openSession"
          @delete="confirmDelete"
        />
      </div>
    </main>

    <CreateSessionModal
      v-if="showCreateModal"
      :templates="store.templates"
      @close="showCreateModal = false"
      @create="handleCreate"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useSessionStore } from '../stores/session.js';
import SessionCard from '../components/sessions/SessionCard.vue';
import CreateSessionModal from '../components/sessions/CreateSessionModal.vue';

const router = useRouter();
const store = useSessionStore();
const showCreateModal = ref(false);

onMounted(async () => {
  await Promise.all([store.fetchSessions(), store.fetchTemplates()]);
});

function openSession(id) {
  router.push({ name: 'session', params: { id } });
}

async function handleCreate({ templateId, title }) {
  const session = await store.createSession({ templateId, title });
  if (session) {
    showCreateModal.value = false;
    router.push({ name: 'session', params: { id: session.id } });
  }
}

async function confirmDelete(id) {
  if (window.confirm('Delete this session? This cannot be undone.')) {
    await store.deleteSession(id);
  }
}
</script>
