<template>
  <Teleport to="body">
    <div class="fixed inset-0 bg-bg-overlay backdrop-blur-sm flex items-center justify-center z-50 p-4" @click.self="$emit('close')">
      <div class="bg-bg-secondary border border-border rounded-2xl w-full max-w-xl flex flex-col shadow-2xl max-h-[85vh]">
        <div class="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 class="text-lg font-semibold">Import Character Card</h2>
          <button class="text-text-muted hover:text-text-primary transition-colors cursor-pointer" :disabled="loading" @click="$emit('close')">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="flex gap-1 px-5 pt-3">
          <button
            class="px-3 py-1.5 text-xs rounded-t-md border-b-2 transition-colors cursor-pointer"
            :class="tab === 'url'
              ? 'border-accent text-text-primary'
              : 'border-transparent text-text-muted hover:text-text-secondary'"
            @click="tab = 'url'"
          >Chub URL</button>
          <button
            class="px-3 py-1.5 text-xs rounded-t-md border-b-2 transition-colors cursor-pointer"
            :class="tab === 'file'
              ? 'border-accent text-text-primary'
              : 'border-transparent text-text-muted hover:text-text-secondary'"
            @click="tab = 'file'"
          >JSON File</button>
        </div>

        <div class="px-5 py-4 flex-1 overflow-y-auto">
          <div v-if="tab === 'url'" class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Chub.ai URL</label>
            <input v-model="url" placeholder="https://chub.ai/characters/username/character-name"
              :disabled="loading"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm font-mono
                     focus:outline-none focus:border-accent transition-colors disabled:opacity-50" />
            <p class="text-xs text-text-muted mt-1">The card will be fetched, then an LLM call converts it into a PenDrift template (takes 20-60s).</p>
          </div>

          <div v-else class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Character Card File</label>
            <div class="flex items-center gap-2">
              <input ref="fileInput" type="file" accept=".json,application/json"
                :disabled="loading"
                class="hidden"
                @change="onFileChosen" />
              <button
                class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-secondary text-sm
                       hover:border-accent/40 hover:text-text-primary transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 disabled:opacity-50"
                :disabled="loading"
                @click="fileInput?.click()"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
                </svg>
                Choose .json
              </button>
              <span class="flex-1 text-xs font-mono text-text-secondary truncate">
                {{ fileName || 'No file selected' }}
              </span>
              <button
                v-if="fileName"
                class="text-text-muted hover:text-accent transition-colors p-1"
                :disabled="loading"
                @click="clearFile"
                title="Clear"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <p class="text-xs text-text-muted mt-1">Pick a TavernAI/SillyTavern V2 card JSON file from your disk. Supports raw card or wrapped in {spec, data}.</p>
          </div>

          <div class="mt-4 flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Conversion Preset</label>
            <select v-model="presetId" :disabled="loading"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors disabled:opacity-50">
              <option v-for="p in presets" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
            <p class="text-xs text-text-muted">Uses `chubImportPrompt` from this preset. A model must be loaded.</p>
          </div>

          <div v-if="error" class="mt-4 p-3 bg-error/10 border border-error/30 rounded-lg text-sm text-error">{{ error }}</div>
        </div>

        <div class="px-5 py-3 border-t border-border flex items-center justify-end gap-3">
          <button
            class="px-4 py-2 border border-border rounded-lg text-text-secondary text-sm cursor-pointer
                   hover:bg-bg-surface hover:text-text-primary transition-all disabled:opacity-50"
            :disabled="loading"
            @click="$emit('close')"
          >Cancel</button>
          <button
            class="px-5 py-2 bg-accent rounded-lg text-white text-sm font-semibold cursor-pointer
                   hover:bg-accent-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
            :disabled="loading || !canSubmit"
            @click="submit"
          >
            <svg v-if="loading" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-opacity="0.25" stroke-width="4" />
              <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
            </svg>
            {{ loading ? 'Converting via LLM...' : 'Import & Edit' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { useSettingsStore } from '../../stores/settings.js';
import * as importApi from '../../api/import.js';

const emit = defineEmits(['close', 'imported']);

const store = useSettingsStore();
const tab = ref('url');
const url = ref('');
const fileInput = ref(null);
const fileName = ref('');
const fileCard = ref(null);
const presetId = ref('default');
const loading = ref(false);
const error = ref('');

const presets = computed(() => store.presets);

const canSubmit = computed(() => {
  if (tab.value === 'url') return url.value.trim().length > 0;
  return fileCard.value !== null;
});

function onFileChosen(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  error.value = '';
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      fileCard.value = JSON.parse(e.target.result);
      fileName.value = file.name;
    } catch {
      error.value = `Invalid JSON in ${file.name}`;
      clearFile();
    }
  };
  reader.onerror = () => {
    error.value = 'Could not read file';
    clearFile();
  };
  reader.readAsText(file);
}

function clearFile() {
  fileCard.value = null;
  fileName.value = '';
  if (fileInput.value) fileInput.value.value = '';
}

onMounted(async () => {
  if (!store.presets.length) await store.fetchPresets();
  // Default to the preset flagged as default (★) so first-time imports
  // pick up the user's preferred model + chubImportPrompt override
  presetId.value = store.defaultPresetId();
});

async function submit() {
  error.value = '';
  loading.value = true;
  try {
    const payload = { settingsPresetId: presetId.value };
    if (tab.value === 'url') {
      payload.url = url.value.trim();
    } else {
      payload.card = fileCard.value;
    }
    // Backend returns immediately with a jobId; the actual import runs in
    // the background and the JobsToastBar shows live progress. The parent
    // (TemplatesView) watches for the job to complete and refreshes its
    // list at that point.
    const result = await importApi.importChub(payload);
    emit('queued', { jobId: result.jobId, originalCard: result.originalCard });
  } catch (err) {
    const body = err?.response && typeof err.response.json === 'function'
      ? await err.response.json().catch(() => null)
      : null;
    error.value = body?.detail || err?.message || 'Import failed';
    loading.value = false;
    return;
  }
  loading.value = false;
}
</script>
