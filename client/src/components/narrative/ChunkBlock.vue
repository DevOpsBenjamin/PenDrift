<template>
  <div
    class="group relative pb-6 mb-6 border-b border-border-subtle last:border-b-0 last:mb-0"
    :class="{ 'pl-4 border-l-2 border-l-accent': chunk.isKeyMoment }"
  >
    <!-- Top-right icons -->
    <div class="absolute -right-1 top-0 flex gap-1 opacity-30 group-hover:opacity-100 transition-opacity">
      <button
        v-if="chunk.thinking"
        class="p-1 text-text-muted hover:text-accent transition-colors cursor-pointer"
        @click="showThinking = true"
        title="View model reasoning"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
      </button>
      <button
        class="p-1 text-text-muted hover:text-accent transition-colors cursor-pointer"
        @click="startEdit"
        title="Edit chunk"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
        </svg>
      </button>
    </div>

    <!-- Chunk metadata line -->
    <div class="flex items-center gap-3 mb-2 text-[10px] text-text-muted/40 font-ui select-none">
      <span v-if="chunk.stats?.durationMs">{{ (chunk.stats.durationMs / 1000).toFixed(1) }}s</span>
      <span v-if="chunk.stats?.completionTokens">{{ chunk.stats.completionTokens }} tok</span>
      <span v-if="chunk.stats?.reasoningTokens" class="text-text-muted/30">{{ chunk.stats.reasoningTokens }} think</span>
      <span v-if="chunk.editedAt" class="text-accent/30">edited</span>
    </div>

    <!-- Thinking popup -->
    <ThinkingPanel
      v-if="showThinking"
      :thinking="chunk.thinking"
      @close="showThinking = false"
    />

    <!-- Edit mode -->
    <div v-if="editing" class="flex flex-col gap-3">
      <textarea
        ref="editArea"
        v-model="editValue"
        class="w-full px-4 py-3 bg-bg-primary border border-accent/30 rounded-xl text-text-primary
               font-body text-base leading-relaxed resize-y min-h-48 focus:outline-none focus:border-accent/60"
      ></textarea>
      <div class="flex gap-2 justify-end">
        <button
          class="px-3 py-1.5 text-xs border border-border rounded-md text-text-secondary
                 hover:bg-bg-surface hover:text-text-primary transition-all cursor-pointer"
          @click="editing = false"
        >Cancel</button>
        <button
          class="px-4 py-1.5 text-xs bg-accent rounded-md text-white font-semibold
                 hover:bg-accent-hover transition-colors cursor-pointer"
          @click="saveEdit"
        >Save</button>
      </div>
    </div>

    <!-- Display mode -->
    <div v-else class="prose-narrative" v-html="formattedNarrative"></div>

    <!-- Last chunk actions -->
    <div
      v-if="isLast && !editing"
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
import { ref, computed, nextTick } from 'vue';
import { renderNarrative } from '../../utils/narrative-renderer.js';
import ThinkingPanel from './ThinkingPanel.vue';

const props = defineProps({
  chunk: Object,
  isLast: Boolean,
});

const emit = defineEmits(['regenerate', 'delete', 'edit']);

const showThinking = ref(false);
const editing = ref(false);
const editValue = ref('');
const editArea = ref(null);

const formattedNarrative = computed(() => renderNarrative(props.chunk?.narrative));

function startEdit() {
  editValue.value = props.chunk.narrative;
  editing.value = true;
  nextTick(() => editArea.value?.focus());
}

function saveEdit() {
  if (editValue.value.trim()) {
    emit('edit', { chunkId: props.chunk.id, narrative: editValue.value.trim() });
  }
  editing.value = false;
}
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

.narrative-dialogue {
  color: #e8b87a;
}

.narrative-thought {
  color: #8eafc2;
  font-style: italic;
}

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
