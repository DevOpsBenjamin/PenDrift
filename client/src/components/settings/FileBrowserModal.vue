<template>
  <Teleport to="body">
    <div class="fixed inset-0 bg-bg-overlay backdrop-blur-sm flex items-center justify-center z-50 p-4" @click.self="$emit('close')">
      <div class="bg-bg-secondary border border-border rounded-2xl w-full max-w-2xl flex flex-col shadow-2xl max-h-[80vh]">
        <div class="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 class="text-lg font-semibold">Select GGUF Model</h2>
          <button class="text-text-muted hover:text-text-primary transition-colors cursor-pointer" @click="$emit('close')">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="px-5 py-3 border-b border-border-subtle flex items-center gap-2">
          <button
            class="px-2 py-1 text-xs bg-bg-surface border border-border rounded text-text-secondary
                   hover:border-accent/40 hover:text-text-primary transition-all cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
            :disabled="!data?.parent || loading"
            @click="navigate(data.parent)"
            title="Parent directory"
          >↑ Up</button>
          <button
            class="px-2 py-1 text-xs bg-bg-surface border border-border rounded text-text-secondary
                   hover:border-accent/40 hover:text-text-primary transition-all cursor-pointer"
            :disabled="loading"
            @click="navigate(null)"
            title="Root / drives"
          >⌂ Root</button>
          <div class="flex-1 px-3 py-1 bg-bg-primary border border-border-subtle rounded text-xs font-mono text-text-secondary truncate">
            {{ data?.currentPath || '—' }}
          </div>
        </div>

        <div class="flex-1 overflow-y-auto px-5 py-3 min-h-48">
          <div v-if="loading" class="text-center text-text-muted text-sm py-8">Loading...</div>
          <div v-else-if="error" class="text-center text-error text-sm py-8">{{ error }}</div>
          <div v-else-if="!data?.directories?.length && !data?.files?.length" class="text-center text-text-muted text-sm py-8 italic">
            Empty directory (no subfolders or .gguf files)
          </div>
          <ul v-else class="flex flex-col gap-0.5">
            <li
              v-for="dir in data.directories"
              :key="'d:' + dir"
              class="flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer text-sm text-text-secondary
                     hover:bg-bg-surface hover:text-text-primary transition-colors"
              @click="navigate(joinPath(data.currentPath, dir))"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-accent/70 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path d="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
              </svg>
              <span class="truncate">{{ dir }}</span>
            </li>
            <li
              v-for="file in data.files"
              :key="'f:' + file.name"
              class="flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer text-sm text-text-primary
                     hover:bg-accent/10 transition-colors"
              @click="selectFile(file.name)"
              @dblclick="selectAndConfirm(file.name)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-text-muted shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span class="flex-1 truncate font-mono">{{ file.name }}</span>
              <span class="text-xs text-text-muted shrink-0">{{ formatSize(file.size) }}</span>
            </li>
          </ul>
        </div>

        <div class="px-5 py-3 border-t border-border flex items-center justify-between gap-3">
          <div class="text-xs text-text-muted truncate flex-1">
            <template v-if="selected">Selected: <span class="font-mono text-text-secondary">{{ selected }}</span></template>
            <template v-else>Click a .gguf file to select it</template>
          </div>
          <button
            class="px-4 py-2 border border-border rounded-lg text-text-secondary text-sm cursor-pointer
                   hover:bg-bg-surface hover:text-text-primary transition-all"
            @click="$emit('close')"
          >Cancel</button>
          <button
            class="px-5 py-2 bg-accent rounded-lg text-white text-sm font-semibold cursor-pointer
                   hover:bg-accent-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            :disabled="!selected"
            @click="confirm"
          >Select</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import * as llmApi from '../../api/llm.js';

const props = defineProps({ initialPath: String });
const emit = defineEmits(['close', 'select']);

const data = ref(null);
const loading = ref(false);
const error = ref('');
const selected = ref('');

async function navigate(path) {
  loading.value = true;
  error.value = '';
  selected.value = '';
  try {
    data.value = await llmApi.browsePath(path || '');
  } catch (err) {
    error.value = err?.message || 'Failed to load directory';
    data.value = null;
  } finally {
    loading.value = false;
  }
}

function joinPath(base, name) {
  if (!base) return name;
  const sep = base.includes('\\') || /^[A-Z]:$/i.test(base.replace(/\\$/, '')) ? '\\' : '/';
  const trimmed = base.endsWith(sep) ? base.slice(0, -1) : base;
  return trimmed + sep + name;
}

function selectFile(name) {
  selected.value = joinPath(data.value.currentPath, name);
}

function selectAndConfirm(name) {
  selectFile(name);
  confirm();
}

function confirm() {
  if (selected.value) emit('select', selected.value);
}

function formatSize(bytes) {
  if (!bytes) return '';
  const gb = bytes / 1024 / 1024 / 1024;
  if (gb >= 1) return gb.toFixed(1) + ' GB';
  const mb = bytes / 1024 / 1024;
  return mb.toFixed(0) + ' MB';
}

onMounted(() => {
  const start = props.initialPath
    ? props.initialPath.replace(/[\\/][^\\/]+$/, '')
    : '';
  navigate(start);
});
</script>
