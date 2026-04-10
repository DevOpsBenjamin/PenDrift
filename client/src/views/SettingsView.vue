<template>
  <div class="settings-page">
    <div class="page-header">
      <h1>Settings Presets</h1>
      <button class="btn-new" @click="startNew">+ New Preset</button>
    </div>

    <div class="layout">
      <aside class="preset-list">
        <div
          v-for="preset in store.presets"
          :key="preset.id"
          class="preset-item"
          :class="{ active: editing?.id === preset.id }"
          @click="edit(preset)"
        >
          <span>{{ preset.name }}</span>
          <button
            v-if="preset.id !== 'default'"
            class="btn-delete"
            @click.stop="remove(preset.id)"
          >x</button>
        </div>
      </aside>

      <div v-if="editing" class="editor">
        <div class="field">
          <label>ID (unique, no spaces)</label>
          <input v-model="editing.id" :disabled="!isNew" />
        </div>
        <div class="field">
          <label>Name</label>
          <input v-model="editing.name" />
        </div>
        <div class="field">
          <label>API Endpoint</label>
          <input v-model="editing.apiEndpoint" placeholder="http://localhost:11434/v1/chat/completions" />
        </div>
        <div class="field">
          <label>Model</label>
          <input v-model="editing.model" placeholder="qwen2.5:14b" />
        </div>
        <div class="field-row">
          <div class="field">
            <label>Temperature</label>
            <input v-model.number="editing.temperature" type="number" step="0.1" min="0" max="2" />
          </div>
          <div class="field">
            <label>Max Tokens</label>
            <input v-model.number="editing.maxTokens" type="number" step="256" min="256" />
          </div>
          <div class="field">
            <label>Context Size</label>
            <input v-model.number="editing.contextSize" type="number" step="1024" min="1024" />
          </div>
        </div>
        <div class="field-row">
          <div class="field">
            <label>Character Update Interval (chunks)</label>
            <input v-model.number="editing.chunkUpdateInterval" type="number" min="1" />
          </div>
          <div class="field">
            <label>Think Block Start</label>
            <input v-model="editing.thinkBlockStart" />
          </div>
          <div class="field">
            <label>Think Block End</label>
            <input v-model="editing.thinkBlockEnd" />
          </div>
        </div>
        <div class="field">
          <label>System Prompt</label>
          <textarea v-model="editing.systemPrompt" rows="8"></textarea>
        </div>
        <div class="actions">
          <button class="btn-cancel" @click="editing = null">Cancel</button>
          <button class="btn-save" @click="save">Save</button>
        </div>
      </div>

      <div v-else class="empty-editor">
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

<style scoped>
.settings-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 2rem 1.5rem;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

h1 {
  font-family: var(--font-body);
  font-size: 1.8rem;
}

.btn-new {
  padding: 0.6rem 1.25rem;
  background: var(--color-accent);
  border: none;
  border-radius: 6px;
  color: white;
  cursor: pointer;
  font-weight: 600;
}

.btn-new:hover {
  background: var(--color-accent-hover);
}

.layout {
  display: flex;
  gap: 1.5rem;
}

.preset-list {
  width: 220px;
  min-width: 220px;
}

.preset-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.6rem 0.75rem;
  border-radius: 6px;
  cursor: pointer;
  color: var(--color-text-secondary);
  font-size: 0.9rem;
  transition: background 0.15s;
}

.preset-item:hover {
  background: var(--color-bg-surface);
}

.preset-item.active {
  background: var(--color-bg-surface);
  color: var(--color-text-primary);
  font-weight: 600;
}

.btn-delete {
  background: none;
  border: none;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.btn-delete:hover {
  color: var(--color-accent);
}

.editor {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.empty-editor {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
  font-style: italic;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.field label {
  font-size: 0.8rem;
  color: var(--color-text-secondary);
}

.field input, .field textarea {
  padding: 0.6rem 0.75rem;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text-primary);
  font-size: 0.9rem;
  font-family: var(--font-ui);
}

.field input:focus, .field textarea:focus {
  outline: none;
  border-color: var(--color-accent);
}

.field input:disabled {
  opacity: 0.5;
}

.field textarea {
  resize: vertical;
  min-height: 120px;
}

.field-row {
  display: flex;
  gap: 1rem;
}

.field-row .field {
  flex: 1;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 0.5rem;
}

.btn-cancel {
  padding: 0.5rem 1rem;
  background: none;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.btn-save {
  padding: 0.5rem 1.25rem;
  background: var(--color-accent);
  border: none;
  border-radius: 6px;
  color: white;
  cursor: pointer;
  font-weight: 600;
}

.btn-save:hover {
  background: var(--color-accent-hover);
}
</style>
