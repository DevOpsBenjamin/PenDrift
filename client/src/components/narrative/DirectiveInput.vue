<template>
  <div class="directive-input">
    <div class="input-row">
      <textarea
        ref="textarea"
        v-model="directive"
        placeholder="Write your directive..."
        :disabled="generating"
        @keydown.enter.exact="submit"
        @input="autoResize"
        rows="1"
      ></textarea>
      <button
        class="btn-generate"
        @click="submit"
        :disabled="generating || !directive.trim()"
      >
        {{ generating ? '...' : 'Generate' }}
      </button>
    </div>
    <div class="input-meta">
      <label class="key-moment-toggle">
        <input type="checkbox" v-model="isKeyMoment" />
        Key moment
      </label>
      <span class="hint">Enter to send, Shift+Enter for newline</span>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue';

const props = defineProps({ generating: Boolean });
const emit = defineEmits(['submit']);

const directive = ref('');
const isKeyMoment = ref(false);
const textarea = ref(null);

function submit(e) {
  if (e) e.preventDefault();
  if (!directive.value.trim() || props.generating) return;
  emit('submit', { directive: directive.value.trim(), isKeyMoment: isKeyMoment.value });
  directive.value = '';
  isKeyMoment.value = false;
  nextTick(() => autoResize());
}

function autoResize() {
  if (!textarea.value) return;
  textarea.value.style.height = 'auto';
  textarea.value.style.height = Math.min(textarea.value.scrollHeight, 150) + 'px';
}
</script>

<style scoped>
.directive-input {
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
}

.input-row {
  display: flex;
  gap: 0.75rem;
  align-items: flex-end;
}

textarea {
  flex: 1;
  padding: 0.75rem 1rem;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-text-primary);
  font-family: var(--font-ui);
  font-size: 0.95rem;
  resize: none;
  line-height: 1.5;
  overflow-y: hidden;
}

textarea:focus {
  outline: none;
  border-color: var(--color-accent);
}

textarea:disabled {
  opacity: 0.5;
}

.btn-generate {
  padding: 0.75rem 1.5rem;
  background: var(--color-accent);
  border: none;
  border-radius: 8px;
  color: white;
  cursor: pointer;
  font-weight: 600;
  font-size: 0.95rem;
  white-space: nowrap;
}

.btn-generate:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-generate:hover:not(:disabled) {
  background: var(--color-accent-hover);
}

.input-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 0.5rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.key-moment-toggle {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  cursor: pointer;
}

.key-moment-toggle input {
  accent-color: var(--color-accent);
}

.hint {
  opacity: 0.6;
}
</style>
