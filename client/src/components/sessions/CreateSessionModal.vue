<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <h2>New Session</h2>

      <label>Template</label>
      <select v-model="selectedTemplate">
        <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}</option>
      </select>

      <label>Title (optional)</label>
      <input v-model="title" placeholder="Leave empty to use template name" />

      <div class="actions">
        <button class="btn-cancel" @click="$emit('close')">Cancel</button>
        <button class="btn-create" @click="create" :disabled="!selectedTemplate">Create</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';

const props = defineProps({ templates: Array });
const emit = defineEmits(['close', 'create']);

const selectedTemplate = ref(props.templates[0]?.id || '');
const title = ref('');

function create() {
  emit('create', {
    templateId: selectedTemplate.value,
    title: title.value || undefined,
  });
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 2rem;
  width: 400px;
  max-width: 90vw;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

h2 {
  margin-bottom: 0.5rem;
}

label {
  font-size: 0.85rem;
  color: var(--color-text-secondary);
}

select, input {
  padding: 0.6rem 0.75rem;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text-primary);
  font-size: 0.95rem;
}

select:focus, input:focus {
  outline: none;
  border-color: var(--color-accent);
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

.btn-create {
  padding: 0.5rem 1.25rem;
  background: var(--color-accent);
  border: none;
  border-radius: 6px;
  color: white;
  cursor: pointer;
  font-weight: 600;
}

.btn-create:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-create:hover:not(:disabled) {
  background: var(--color-accent-hover);
}
</style>
