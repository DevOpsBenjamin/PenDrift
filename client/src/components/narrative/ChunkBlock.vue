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
import { renderNarrative } from '../../utils/narrative-renderer.js';

const props = defineProps({
  chunk: Object,
  isLast: Boolean,
});

defineEmits(['regenerate', 'delete']);

const formattedNarrative = computed(() => renderNarrative(props.chunk?.narrative));
</script>

<style>
/* Narrative prose — unscoped for v-html */
.prose-narrative {
  font-family: var(--font-body);
  font-size: 1.1rem;
  line-height: 1.9;
  color: var(--color-text-primary);
}

.prose-narrative p {
  margin-bottom: 0.85rem;
}

.prose-narrative em {
  color: var(--color-text-secondary);
  font-style: italic;
}

.prose-narrative strong {
  color: var(--color-text-primary);
  font-weight: 700;
}

/* "Dialogue" — warm accent color */
.narrative-dialogue {
  color: #e8b87a;
}

/* 'Inner monologue / thoughts' — muted italic */
.narrative-thought {
  color: #8eafc2;
  font-style: italic;
}

/* Scene break --- */
.narrative-scene-break {
  display: flex;
  justify-content: center;
  padding: 1.5rem 0;
}

.narrative-scene-break span {
  display: block;
  width: 80px;
  height: 1px;
  background: linear-gradient(to right, transparent, var(--color-border), transparent);
}

/* Horizontal rule fallback */
.prose-narrative hr {
  border: none;
  margin: 1.5rem 0;
}

@media (max-width: 640px) {
  .prose-narrative {
    font-size: 1rem;
    line-height: 1.75;
  }
}
</style>
