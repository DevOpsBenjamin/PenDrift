<template>
  <div
    class="group relative pb-6 mb-6 border-b border-border-subtle last:border-b-0 last:mb-0"
    :class="{ 'pl-4 border-l-2 border-l-accent': chunk.isKeyMoment }"
  >
    <div class="prose-narrative" v-html="formattedNarrative"></div>
    <div
      v-if="isLast"
      class="flex gap-2 mt-4 opacity-0 group-hover:opacity-100 transition-opacity duration-200
             sm:opacity-0 max-sm:opacity-100"
    >
      <button
        class="px-3 py-1.5 text-xs bg-bg-surface border border-border rounded-md text-text-secondary
               hover:text-accent hover:border-accent/40 transition-all cursor-pointer"
        @click="$emit('regenerate')"
      >Retry</button>
      <button
        class="px-3 py-1.5 text-xs bg-bg-surface border border-border rounded-md text-text-secondary
               hover:text-error hover:border-error/40 transition-all cursor-pointer"
        @click="$emit('delete')"
      >Delete</button>
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
  return props.chunk.narrative
    .split('\n\n')
    .map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`)
    .join('');
});
</script>

<style>
/* Narrative prose styling — unscoped so v-html works */
.prose-narrative p {
  font-family: var(--font-body);
  font-size: 1.1rem;
  line-height: 1.9;
  margin-bottom: 0.85rem;
  color: var(--color-text-primary);
}

@media (max-width: 640px) {
  .prose-narrative p {
    font-size: 1rem;
    line-height: 1.75;
  }
}
</style>
