<template>
  <div
    class="group relative pb-6 mb-6 border-b border-border-subtle last:border-b-0 last:mb-0"
    :class="{ 'pl-4 border-l-2 border-l-accent': chunk.isKeyMoment }"
  >
    <!-- Thinking icon -->
    <button
      v-if="chunk.thinking"
      class="absolute -right-1 top-0 p-1 text-text-muted hover:text-accent transition-colors cursor-pointer
             opacity-30 group-hover:opacity-100"
      @click="showThinking = !showThinking"
      title="View model reasoning"
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
      </svg>
    </button>

    <!-- Thinking panel -->
    <div
      v-if="showThinking"
      class="mb-4 p-3 bg-bg-surface/50 border border-border-subtle rounded-lg text-xs text-text-muted
             leading-relaxed max-h-64 overflow-y-auto whitespace-pre-wrap font-ui"
    >{{ chunk.thinking }}</div>

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
import { ref, computed } from 'vue';
import { renderNarrative } from '../../utils/narrative-renderer.js';

const props = defineProps({
  chunk: Object,
  isLast: Boolean,
});

defineEmits(['regenerate', 'delete']);

const showThinking = ref(false);
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
