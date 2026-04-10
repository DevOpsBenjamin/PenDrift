<template>
  <div class="session-card" @click="$emit('select', session.id)">
    <div class="card-header">
      <h3>{{ session.title }}</h3>
      <button class="delete-btn" @click.stop="$emit('delete', session.id)" title="Delete session">x</button>
    </div>
    <div class="card-meta">
      <span>{{ session.chapters?.length || 0 }} chapter(s)</span>
      <span>{{ formatDate(session.updatedAt) }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({ session: Object });
defineEmits(['select', 'delete']);

function formatDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}
</script>

<style scoped>
.session-card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 1.25rem;
  cursor: pointer;
  transition: border-color 0.2s, transform 0.1s;
}

.session-card:hover {
  border-color: var(--color-accent);
  transform: translateY(-1px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: start;
}

h3 {
  font-size: 1.1rem;
  margin-bottom: 0.5rem;
}

.delete-btn {
  background: none;
  border: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 1rem;
  padding: 0 0.25rem;
  line-height: 1;
}

.delete-btn:hover {
  color: var(--color-accent);
}

.card-meta {
  display: flex;
  justify-content: space-between;
  font-size: 0.8rem;
  color: var(--color-text-secondary);
}
</style>
