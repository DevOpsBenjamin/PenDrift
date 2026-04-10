<template>
  <div class="flex-1 max-w-5xl mx-auto px-4 sm:px-6 py-6 sm:py-10 w-full">
    <div class="flex items-center justify-between mb-6 sm:mb-8">
      <h1 class="font-body text-2xl sm:text-3xl font-bold">Settings Presets</h1>
      <button
        class="px-4 py-2.5 bg-accent rounded-lg text-white text-sm font-semibold cursor-pointer
               hover:bg-accent-hover transition-colors active:scale-95"
        @click="startNew"
      >+ New Preset</button>
    </div>

    <div class="flex flex-col md:flex-row gap-6">
      <!-- Preset list -->
      <aside class="md:w-56 md:min-w-56 flex md:flex-col gap-2 overflow-x-auto md:overflow-x-visible pb-2 md:pb-0">
        <div
          v-for="preset in store.presets"
          :key="preset.id"
          class="group flex items-center justify-between gap-2 px-3 py-2 rounded-lg cursor-pointer text-sm whitespace-nowrap
                 transition-all duration-150"
          :class="editing?.id === preset.id
            ? 'bg-bg-surface text-text-primary font-medium'
            : 'text-text-secondary hover:bg-bg-surface/50'"
          @click="edit(preset)"
        >
          <span class="truncate">{{ preset.name }}</span>
          <button
            class="opacity-0 group-hover:opacity-100 text-text-muted hover:text-accent transition-all shrink-0"
            @click.stop="duplicate(preset)"
            title="Duplicate"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </button>
        </div>
      </aside>

      <!-- Editor -->
      <div v-if="editing" class="flex-1 flex flex-col gap-4">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">ID</label>
            <input v-model="editing.id" :disabled="!isNew"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors disabled:opacity-40" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Name</label>
            <input v-model="editing.name"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
        </div>

        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-text-muted font-medium uppercase tracking-wider">API Endpoint</label>
          <input v-model="editing.apiEndpoint" placeholder="http://localhost:11434/v1/chat/completions"
            class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors" />
        </div>

        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Model</label>
          <input v-model="editing.model" placeholder="qwen2.5:14b"
            class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors" />
        </div>

        <div class="grid grid-cols-3 gap-3">
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Temp</label>
            <input v-model.number="editing.temperature" type="number" step="0.1" min="0" max="2"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Max Tokens</label>
            <input v-model.number="editing.maxTokens" type="number" step="256" min="256"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Context</label>
            <input v-model.number="editing.contextSize" type="number" step="1024" min="1024"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Update Interval</label>
            <input v-model.number="editing.chunkUpdateInterval" type="number" min="1"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Think Start</label>
            <input v-model="editing.thinkBlockStart"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm font-mono
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Think End</label>
            <input v-model="editing.thinkBlockEnd"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm font-mono
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
        </div>

        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-text-muted font-medium uppercase tracking-wider">System Prompt</label>
          <textarea v-model="editing.systemPrompt" rows="6"
            class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   font-ui resize-y min-h-32 focus:outline-none focus:border-accent transition-colors"></textarea>
        </div>

        <div class="flex justify-between pt-2">
          <button
            v-if="!isNew && editing.id !== 'default'"
            class="px-4 py-2 border border-error/30 rounded-lg text-error text-sm
                   hover:bg-error/10 transition-all cursor-pointer"
            @click="remove(editing.id)"
          >Delete</button>
          <span v-else></span>
          <div class="flex gap-3">
            <button
              class="px-4 py-2 border border-border rounded-lg text-text-secondary text-sm
                     hover:bg-bg-surface hover:text-text-primary transition-all cursor-pointer"
              @click="editing = null"
            >Cancel</button>
            <button
              class="px-5 py-2 bg-accent rounded-lg text-white text-sm font-semibold
                     hover:bg-accent-hover transition-colors cursor-pointer active:scale-95"
              @click="save"
            >Save</button>
          </div>
        </div>
      </div>

      <div v-else class="flex-1 flex items-center justify-center text-text-muted italic text-sm py-20">
        Select a preset to edit or create a new one.
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { useSettingsStore } from '../stores/settings.js';

const store = useSettingsStore();
const editing = ref(null);
const isNew = ref(false);

onMounted(() => store.fetchPresets());

function edit(preset) {
  editing.value = JSON.parse(JSON.stringify(preset));
  isNew.value = false;
}

function duplicate(preset) {
  const copy = JSON.parse(JSON.stringify(preset));
  copy.id = copy.id + '_copy';
  copy.name = copy.name + ' (copy)';
  editing.value = copy;
  isNew.value = true;
}

function startNew() {
  isNew.value = true;
  editing.value = {
    id: '',
    name: '',
    apiEndpoint: 'http://localhost:11434/v1/chat/completions',
    model: 'qwen2.5:14b',
    temperature: 0.8,
    maxTokens: 2048,
    contextSize: 8192,
    chunkUpdateInterval: 10,
    thinkBlockStart: '<think>',
    thinkBlockEnd: '</think>',
    systemPrompt: '',
  };
}

async function save() {
  if (!editing.value.id || !editing.value.name) return;
  const saved = await store.savePreset(editing.value);
  if (saved) {
    editing.value = JSON.parse(JSON.stringify(saved));
    isNew.value = false;
  }
}

async function remove(id) {
  if (window.confirm('Delete this preset?')) {
    await store.deletePreset(id);
    if (editing.value?.id === id) editing.value = null;
  }
}
</script>
