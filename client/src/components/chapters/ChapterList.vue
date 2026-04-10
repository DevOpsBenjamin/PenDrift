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
          <span class="flex-1 truncate">{{ chapter.title }}</span>
          <button
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
    <button
      class="w-full mt-2 py-2 border border-dashed border-border rounded-lg text-text-muted text-xs
             hover:border-accent/40 hover:text-accent transition-all cursor-pointer"
      @click="$emit('create')"
    >+ New Chapter</button>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue';

defineProps({
  chapters: Array,
  currentChapterId: String,
});

const emit = defineEmits(['select', 'create', 'rename']);

const renamingId = ref(null);
const renameValue = ref('');
const renameInput = ref(null);

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
