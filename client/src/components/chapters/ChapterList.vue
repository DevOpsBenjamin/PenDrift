<template>
  <div class="p-3">
    <h3 class="text-[11px] font-semibold uppercase tracking-widest text-text-muted mb-3">Chapters</h3>
    <ul class="space-y-0.5">
      <li
        v-for="chapter in chapters"
        :key="chapter.id"
        class="group flex items-center gap-1 px-3 py-2 rounded-lg cursor-pointer text-sm transition-all duration-150"
        :class="chapter.id === currentChapterId
          ? 'bg-bg-surface text-text-primary font-medium'
          : 'text-text-secondary hover:bg-bg-surface/50 hover:text-text-primary'"
        @click="$emit('select', chapter.id)"
      >
        <template v-if="renamingId === chapter.id">
          <input
            ref="renameInput"
            v-model="renameValue"
            class="flex-1 bg-bg-primary border border-accent/50 rounded px-2 py-0.5 text-sm text-text-primary
                   focus:outline-none"
            @keydown.enter="submitRename(chapter.id)"
            @keydown.escape="renamingId = null"
            @blur="submitRename(chapter.id)"
            @click.stop
          />
        </template>
        <template v-else>
          <!-- Lock icon for finalized chapters -->
          <svg v-if="chapter.finalized" xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 text-text-muted/50 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
          <span class="flex-1 truncate">{{ chapter.title }}</span>
          <!-- Regen title for finalized chapters -->
          <button
            v-if="chapter.finalized"
            class="opacity-0 group-hover:opacity-100 text-text-muted hover:text-accent transition-all shrink-0 p-0.5"
            @click.stop="$emit('regenTitle', chapter.id)"
            title="Regenerate title"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
          <!-- Rename for non-finalized -->
          <button
            v-if="!chapter.finalized"
            class="opacity-0 group-hover:opacity-100 text-text-muted hover:text-accent transition-all shrink-0 p-0.5"
            @click.stop="startRename(chapter)"
            title="Rename"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
            </svg>
          </button>
        </template>
      </li>
    </ul>

    <!-- Finalize button — only on active non-finalized chapter, NOT in finished/epilogue mode -->
    <button
      v-if="activeChapter && !activeChapter.finalized && !sessionFinished && !isEpilogueLastChapter"
      class="w-full mt-3 py-2 border border-accent/30 rounded-lg text-accent text-xs font-medium
             hover:bg-accent/10 transition-all cursor-pointer"
      :class="{ 'opacity-50 cursor-wait': finalizing }"
      :disabled="finalizing"
      @click="$emit('finalize')"
    >{{ finalizing ? 'Finalizing...' : 'Finalize Chapter' }}</button>

    <!-- Finish Session — generates the epilogue as its own dedicated "Epilogue"
         chapter. Visible only when the trailing chapter is finalized (or empty,
         which means it's the auto-created chapter from the previous finalize
         and will be dropped). If the trailing chapter has chunks but isn't
         finalized, the user must Finalize it first — Finish stays hidden. -->
    <button
      v-if="canFinish"
      class="w-full mt-2 py-2 border border-purple-400/40 rounded-lg text-purple-300 text-xs font-medium
             hover:bg-purple-400/10 transition-all cursor-pointer flex items-center justify-center gap-1.5"
      :class="{ 'opacity-50 cursor-wait': finishing }"
      :disabled="finishing"
      @click="$emit('finish')"
      title="Generate the epilogue — a 10-14 paragraph closing scene with a time jump that resolves each character's arc."
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
      </svg>
      {{ finishing ? 'Generating epilogue…' : 'Finish Session' }}
    </button>

    <!-- Validate & Lock — visible once the Epilogue chapter exists and we're not yet finished -->
    <button
      v-if="!sessionFinished && isEpilogueLastChapter"
      class="w-full mt-2 py-2 bg-purple-500/20 border border-purple-400/60 rounded-lg text-purple-200 text-xs font-semibold
             hover:bg-purple-500/30 transition-all cursor-pointer flex items-center justify-center gap-1.5"
      :class="{ 'opacity-50 cursor-wait': validating }"
      :disabled="validating"
      @click="$emit('validateFinish')"
      title="Lock this session as finished. The currently-active version of every chunk becomes THE version — version switching is disabled in finished mode."
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
      </svg>
      {{ validating ? 'Locking…' : 'Validate & Lock' }}
    </button>

    <!-- Re-trigger Finish if the Epilogue chapter exists but has no chunks (interrupted generation) -->
    <button
      v-if="!sessionFinished && isEpilogueLastChapter && !lastChapterHasChunks"
      class="w-full mt-2 py-2 border border-border-subtle rounded-lg text-text-muted text-xs
             hover:text-text-secondary hover:border-border transition-all cursor-pointer"
      :disabled="finishing"
      @click="$emit('finish')"
    >{{ finishing ? 'Generating…' : 'Generate epilogue' }}</button>

    <!-- Reopen — only when finished -->
    <button
      v-if="sessionFinished"
      class="w-full mt-3 py-2 border border-border rounded-lg text-text-secondary text-xs
             hover:text-text-primary hover:border-accent/40 transition-all cursor-pointer"
      :disabled="reopening"
      @click="$emit('reopen')"
      title="Unlock the session — generation and version switching become available again. The epilogue chunk stays in place."
    >{{ reopening ? 'Reopening…' : 'Reopen Session' }}</button>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue';

const props = defineProps({
  chapters: Array,
  currentChapterId: String,
  finalizing: Boolean,
  sessionFinished: Boolean,
  finishing: Boolean,
  validating: Boolean,
  reopening: Boolean,
});

const emit = defineEmits(['select', 'rename', 'finalize', 'regenTitle', 'finish', 'validateFinish', 'reopen']);

const renamingId = ref(null);
const renameValue = ref('');
const renameInput = ref(null);

const activeChapter = computed(() => props.chapters?.find(c => c.id === props.currentChapterId));
const lastChapter = computed(() => props.chapters?.[props.chapters.length - 1]);
const isEpilogueLastChapter = computed(() => lastChapter.value?.title === 'Epilogue');
// Per-chapter chunkCount comes from the sessions API response.
const lastChapterChunks = computed(() => lastChapter.value?.chunkCount ?? 0);
const lastChapterHasChunks = computed(() => lastChapterChunks.value > 0);
// Finish is allowed when the trailing chapter is either empty (auto-created
// after a previous finalize — backend will drop it) or already finalized.
// A non-finalized chapter with chunks must be Finalized first.
const canFinish = computed(() => {
  if (props.sessionFinished || isEpilogueLastChapter.value) return false;
  const last = lastChapter.value;
  if (!last) return false;
  return last.finalized || lastChapterChunks.value === 0;
});

function startRename(chapter) {
  renamingId.value = chapter.id;
  renameValue.value = chapter.title;
  nextTick(() => {
    renameInput.value?.[0]?.focus();
    renameInput.value?.[0]?.select();
  });
}

function submitRename(chapterId) {
  if (renameValue.value.trim()) {
    emit('rename', { chapterId, title: renameValue.value.trim() });
  }
  renamingId.value = null;
}
</script>
