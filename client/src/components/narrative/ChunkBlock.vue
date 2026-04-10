<template>
  <div class="chunk-block" :class="{ 'key-moment': chunk.isKeyMoment }">
    <div class="chunk-text" v-html="formattedNarrative"></div>
    <div v-if="isLast" class="chunk-actions">
      <button @click="$emit('regenerate')" title="Regenerate">Retry</button>
      <button @click="$emit('delete')" title="Delete">Delete</button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  chunk: Object,
  isLast: Boolean,
});

defineEmits(['regenerate', 'delete']);

const formattedNarrative = computed(() => {
  if (!props.chunk?.narrative) return '';
  // Convert newlines to <br> and wrap paragraphs
  return props.chunk.narrative
    .split('\n\n')
    .map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`)
    .join('');
});
</script>

<style scoped>
.chunk-block {
  position: relative;
  padding: 0 0 1.5rem 0;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 1.5rem;
}

.chunk-block:last-child {
  border-bottom: none;
}

.chunk-block.key-moment {
  border-left: 3px solid var(--color-accent);
  padding-left: 1rem;
}

.chunk-text :deep(p) {
  font-family: var(--font-body);
  font-size: 1.1rem;
  line-height: 1.8;
  margin-bottom: 0.75rem;
  color: var(--color-text-primary);
}

.chunk-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.75rem;
  opacity: 0;
  transition: opacity 0.2s;
}

.chunk-block:hover .chunk-actions {
  opacity: 1;
}

.chunk-actions button {
  padding: 0.3rem 0.75rem;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 0.8rem;
}

.chunk-actions button:hover {
  color: var(--color-accent);
  border-color: var(--color-accent);
}
</style>
