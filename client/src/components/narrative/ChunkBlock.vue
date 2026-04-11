<template>
  <div
    class="group relative pb-6 mb-6 border-b border-border-subtle last:border-b-0 last:mb-0"
    :class="{ 'pl-4 border-l-2 border-l-accent': chunk.isKeyMoment }"
  >
    <!-- Chunk metadata line -->
    <div class="flex items-center justify-between mb-2">
      <div class="flex items-center gap-3 text-[10px] text-text-muted/40 font-ui select-none">
        <span class="text-text-muted/60">#{{ chunkIndex + 1 }}</span>
        <span v-if="activeVer.from" class="text-text-muted/50">{{ activeVer.from }}</span>
        <span v-if="activeVer.stats" class="flex items-center gap-2">
          <span>content: {{ (activeVer.stats.completionTokens || 0) - (activeVer.stats.reasoningTokens || 0) }}</span>
          <span>time: {{ (activeVer.stats.durationMs / 1000).toFixed(1) }}s</span>
          <span v-if="activeVer.stats.reasoningTokens">thinking: {{ activeVer.stats.reasoningTokens }}</span>
        </span>
        <span v-if="!activeVer.stats && activeVer.directive" class="text-accent/30">manually edited</span>
      </div>

      <!-- Action icons -->
      <div class="flex gap-1 opacity-30 group-hover:opacity-100 transition-opacity">
        <button
          v-if="activeVer.directive"
          class="p-1 text-text-muted hover:text-accent transition-colors cursor-pointer"
          @click="showDirective = true"
          title="View directive"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
          </svg>
        </button>
        <button
          v-if="activeVer.thinking"
          class="p-1 text-text-muted hover:text-accent transition-colors cursor-pointer"
          @click="showThinking = true"
          title="View model reasoning"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        </button>
        <button
          v-if="!finalized"
          class="p-1 text-text-muted hover:text-accent transition-colors cursor-pointer"
          @click="startEdit"
          title="Edit chunk"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
          </svg>
        </button>
        <button
          v-if="!finalized"
          class="p-1 text-text-muted hover:text-error transition-colors cursor-pointer"
          @click="confirmDelete"
          title="Delete chunk"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Thinking popup -->
    <ThinkingPanel
      v-if="showThinking"
      :thinking="activeVer.thinking"
      @close="showThinking = false"
    />

    <!-- Directive view popup -->
    <Teleport to="body">
      <div
        v-if="showDirective"
        class="fixed inset-0 bg-bg-overlay backdrop-blur-sm flex items-center justify-center z-50 p-4"
        @click.self="showDirective = false"
      >
        <div class="bg-bg-secondary border border-border rounded-2xl p-6 w-full max-w-lg shadow-2xl">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-lg font-semibold">Directive</h2>
            <button class="text-text-muted hover:text-text-primary transition-colors p-1" @click="showDirective = false">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <p class="text-sm text-text-secondary leading-relaxed italic">{{ activeVer.directive }}</p>
        </div>
      </div>

      <!-- Regenerate modal — editable directive -->
      <div
        v-if="showRegenModal"
        class="fixed inset-0 bg-bg-overlay backdrop-blur-sm flex items-center justify-center z-50 p-4"
        @click.self="showRegenModal = false"
      >
        <div class="bg-bg-secondary border border-border rounded-2xl p-6 w-full max-w-lg shadow-2xl">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-lg font-semibold">Generate New Version</h2>
            <button class="text-text-muted hover:text-text-primary transition-colors p-1" @click="showRegenModal = false">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Directive</label>
          <textarea
            v-model="regenDirective"
            rows="4"
            class="w-full mt-1.5 px-3 py-2.5 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   resize-y focus:outline-none focus:border-accent transition-colors"
          ></textarea>
          <div class="flex justify-end gap-3 mt-4">
            <button
              class="px-4 py-2 border border-border rounded-lg text-text-secondary text-sm
                     hover:bg-bg-surface hover:text-text-primary transition-all cursor-pointer"
              @click="showRegenModal = false"
            >Cancel</button>
            <button
              class="px-5 py-2 bg-accent rounded-lg text-white text-sm font-semibold
                     hover:bg-accent-hover transition-colors cursor-pointer"
              @click="submitRegen"
            >Generate</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Edit mode -->
    <div v-if="editing" class="flex flex-col gap-3">
      <textarea
        ref="editArea"
        v-model="editValue"
        class="w-full px-4 py-3 bg-bg-primary border border-accent/30 rounded-xl text-text-primary
               font-body text-base leading-relaxed resize-y focus:outline-none focus:border-accent/60"
        style="min-height: 60vh"
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
        >Save as new version</button>
      </div>
    </div>

    <!-- Display mode -->
    <div v-else class="prose-narrative" v-html="formattedNarrative"></div>

    <!-- Version swipe arrows — hidden when finalized -->
    <div v-if="!editing && !finalized" class="flex items-center justify-between mt-3">
      <button
        class="w-10 h-10 flex items-center justify-center rounded-full text-lg transition-all cursor-pointer"
        :class="activeIndex > 0
          ? 'text-text-muted hover:text-text-primary hover:bg-bg-surface'
          : 'text-text-muted/15 cursor-default'"
        :disabled="activeIndex <= 0"
        @click="$emit('switchVersion', { chunkId: chunk.id, versionIndex: activeIndex - 1 })"
      >&#9664;</button>
      <span v-if="totalVersions > 1" class="text-xs text-text-muted/50 select-none">{{ activeIndex + 1 }} / {{ totalVersions }}</span>
      <button
        class="w-10 h-10 flex items-center justify-center rounded-full text-lg transition-all cursor-pointer
               text-text-muted hover:text-text-primary hover:bg-bg-surface"
        @click="onSwipeRight"
      >&#9654;</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue';
import { renderNarrative } from '../../utils/narrative-renderer.js';
import ThinkingPanel from './ThinkingPanel.vue';

const props = defineProps({
  chunk: Object,
  chunkIndex: Number,
  isLast: Boolean,
  finalized: Boolean,
});

const emit = defineEmits(['regenerate', 'delete', 'edit', 'switchVersion']);

const showThinking = ref(false);
const showDirective = ref(false);
const showRegenModal = ref(false);
const regenDirective = ref('');
const editing = ref(false);
const editValue = ref('');
const editArea = ref(null);

const activeIndex = computed(() => props.chunk.activeVersion ?? 0);
const totalVersions = computed(() => props.chunk.versions?.length || 1);
const activeVer = computed(() => {
  if (props.chunk.versions?.length) {
    return props.chunk.versions[activeIndex.value];
  }
  return props.chunk;
});

const formattedNarrative = computed(() => renderNarrative(activeVer.value.narrative));

function onSwipeRight() {
  if (activeIndex.value < totalVersions.value - 1) {
    // Navigate to next existing version
    emit('switchVersion', { chunkId: props.chunk.id, versionIndex: activeIndex.value + 1 });
  } else {
    // Past last version — open regen modal
    regenDirective.value = activeVer.value.directive || '';
    showRegenModal.value = true;
  }
}

function submitRegen() {
  showRegenModal.value = false;
  emit('regenerate', { chunkId: props.chunk.id, directive: regenDirective.value.trim() || undefined });
}

function confirmDelete() {
  const msg = totalVersions.value > 1
    ? `Delete this version (${activeIndex.value + 1}/${totalVersions.value})?`
    : 'Delete this chunk?';
  if (window.confirm(msg)) {
    emit('delete', props.chunk.id);
  }
}

function startEdit() {
  editValue.value = activeVer.value.narrative;
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
.prose-narrative {
  font-family: var(--font-body);
  font-size: 1.1rem;
  line-height: 1.9;
  color: var(--color-text-primary);
}
.prose-narrative p { margin-bottom: 0.85rem; }
.prose-narrative em { color: var(--color-text-secondary); font-style: italic; }
.prose-narrative strong { color: var(--color-text-primary); font-weight: 700; }
.narrative-dialogue { color: #e8b87a; }
.narrative-thought { color: #8eafc2; font-style: italic; }
.narrative-scene-break { display: flex; justify-content: center; padding: 1.5rem 0; }
.narrative-scene-break span { display: block; width: 80px; height: 1px; background: linear-gradient(to right, transparent, var(--color-border), transparent); }
.prose-narrative hr { border: none; margin: 1.5rem 0; }
@media (max-width: 640px) { .prose-narrative { font-size: 1rem; line-height: 1.75; } }
</style>
