<template>
  <div class="home">
    <main class="content">
      <div class="content-header">
        <h1>Sessions</h1>
        <button class="btn-new" @click="showCreateModal = true">+ New Session</button>
      </div>

      <div v-if="store.loading" class="loading">Loading...</div>

      <div v-else-if="store.sessions.length === 0" class="empty">
        <p>No sessions yet.</p>
        <p>Create one to start writing.</p>
      </div>

      <div v-else class="session-grid">
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

<style scoped>
.content {
  max-width: 900px;
  margin: 0 auto;
  padding: 2rem 1.5rem;
}

.content-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

h1 {
  font-family: var(--font-body);
  font-size: 1.8rem;
}

.btn-new {
  padding: 0.6rem 1.25rem;
  background: var(--color-accent);
  border: none;
  border-radius: 6px;
  color: white;
  cursor: pointer;
  font-weight: 600;
  font-size: 0.9rem;
}

.btn-new:hover {
  background: var(--color-accent-hover);
}

.loading {
  text-align: center;
  color: var(--color-text-secondary);
  padding: 3rem;
}

.empty {
  text-align: center;
  color: var(--color-text-secondary);
  padding: 4rem 0;
  line-height: 2;
}

.session-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}
</style>
