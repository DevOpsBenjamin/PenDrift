<template>
  <div class="templates-page">
    <div class="page-header">
      <h1>Templates</h1>
      <button class="btn-new" @click="startNew">+ New Template</button>
    </div>

    <div class="layout">
      <aside class="template-list">
        <div
          v-for="tpl in store.templates"
          :key="tpl.id"
          class="template-item"
          :class="{ active: editing?.id === tpl.id }"
          @click="edit(tpl)"
        >
          <span>{{ tpl.name }}</span>
          <button class="btn-delete" @click.stop="remove(tpl.id)">x</button>
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
          <label>Description</label>
          <textarea v-model="editing.description" rows="2"></textarea>
        </div>
        <div class="field">
          <label>Scenario</label>
          <textarea v-model="editing.scenario" rows="4"></textarea>
        </div>
        <div class="field">
          <label>Style Instructions (added to system prompt)</label>
          <textarea v-model="editing.systemPromptAdditions" rows="4"></textarea>
        </div>

        <div class="section">
          <h3>
            Characters
            <button class="btn-add-small" @click="addCharacter">+ Add</button>
          </h3>
          <div v-for="(char, i) in editing.characters" :key="i" class="character-edit">
            <div class="field-row">
              <div class="field" style="flex: 1">
                <label>Name</label>
                <input v-model="char.name" />
              </div>
              <button class="btn-remove" @click="editing.characters.splice(i, 1)">x</button>
            </div>
            <div class="field">
              <label>Description</label>
              <textarea v-model="char.description" rows="3"></textarea>
            </div>
            <div class="field">
              <label>Initial State</label>
              <input v-model="char.initialState" />
            </div>
          </div>
        </div>

        <div class="section">
          <h3>
            Masked Intents
            <button class="btn-add-small" @click="editing.maskedIntents.push('')">+ Add</button>
          </h3>
          <div v-for="(_, i) in editing.maskedIntents" :key="i" class="intent-row">
            <textarea v-model="editing.maskedIntents[i]" rows="2"></textarea>
            <button class="btn-remove" @click="editing.maskedIntents.splice(i, 1)">x</button>
          </div>
        </div>

        <div class="actions">
          <button class="btn-cancel" @click="editing = null">Cancel</button>
          <button class="btn-save" @click="save">Save</button>
        </div>
      </div>

      <div v-else class="empty-editor">
        Select a template to edit or create a new one.
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

onMounted(() => store.fetchTemplates());

function edit(tpl) {
  editing.value = JSON.parse(JSON.stringify(tpl));
  if (!editing.value.characters) editing.value.characters = [];
  if (!editing.value.maskedIntents) editing.value.maskedIntents = [];
  isNew.value = false;
}

function startNew() {
  isNew.value = true;
  editing.value = {
    id: '',
    name: '',
    description: '',
    scenario: '',
    systemPromptAdditions: '',
    characters: [],
    maskedIntents: [],
  };
}

function addCharacter() {
  editing.value.characters.push({ name: '', description: '', initialState: '' });
}

async function save() {
  if (!editing.value.id || !editing.value.name) return;
  // Filter empty masked intents
  editing.value.maskedIntents = editing.value.maskedIntents.filter(i => i.trim());
  const saved = await store.saveTemplate(editing.value);
  if (saved) {
    editing.value = JSON.parse(JSON.stringify(saved));
    isNew.value = false;
  }
}

async function remove(id) {
  if (window.confirm('Delete this template?')) {
    await store.deleteTemplate(id);
    if (editing.value?.id === id) editing.value = null;
  }
}
</script>

<style scoped>
.templates-page {
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

.template-list {
  width: 240px;
  min-width: 240px;
}

.template-item {
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

.template-item:hover {
  background: var(--color-bg-surface);
}

.template-item.active {
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
  max-height: calc(100vh - 150px);
  overflow-y: auto;
  padding-right: 0.5rem;
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
}

.field-row {
  display: flex;
  gap: 0.75rem;
  align-items: flex-end;
}

.section {
  border-top: 1px solid var(--color-border);
  padding-top: 1rem;
}

.section h3 {
  font-size: 0.95rem;
  margin-bottom: 0.75rem;
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.btn-add-small {
  font-size: 0.75rem;
  padding: 0.2rem 0.6rem;
  background: none;
  border: 1px dashed var(--color-border);
  border-radius: 4px;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.btn-add-small:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.character-edit {
  background: var(--color-bg-secondary);
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.intent-row {
  display: flex;
  gap: 0.5rem;
  align-items: flex-start;
  margin-bottom: 0.5rem;
}

.intent-row textarea {
  flex: 1;
  padding: 0.6rem 0.75rem;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text-primary);
  font-size: 0.9rem;
  font-family: var(--font-ui);
  resize: vertical;
}

.intent-row textarea:focus {
  outline: none;
  border-color: var(--color-accent);
}

.btn-remove {
  background: none;
  border: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 1.1rem;
  padding: 0.25rem;
}

.btn-remove:hover {
  color: var(--color-accent);
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 0.5rem;
  padding-bottom: 1rem;
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
