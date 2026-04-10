<template>
  <Teleport to="body">
    <div class="fixed inset-0 bg-bg-overlay backdrop-blur-sm flex items-center justify-center z-50 p-4" @click.self="$emit('close')">
      <div class="bg-bg-secondary border border-border rounded-2xl p-6 w-full max-w-md flex flex-col gap-4 shadow-2xl">
        <h2 class="text-lg font-semibold">New Session</h2>

        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-text-secondary font-medium uppercase tracking-wider">Template</label>
          <select
            v-model="selectedTemplate"
            class="px-3 py-2.5 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   focus:outline-none focus:border-accent transition-colors"
          >
            <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}</option>
          </select>
        </div>

        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-text-secondary font-medium uppercase tracking-wider">Title (optional)</label>
          <input
            v-model="title"
            placeholder="Leave empty to use template name"
            class="px-3 py-2.5 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors"
          />
        </div>

        <div class="flex justify-end gap-3 mt-2">
          <button
            class="px-4 py-2 border border-border rounded-lg text-text-secondary text-sm cursor-pointer
                   hover:bg-bg-surface hover:text-text-primary transition-all"
            @click="$emit('close')"
          >Cancel</button>
          <button
            class="px-5 py-2 bg-accent rounded-lg text-white text-sm font-semibold cursor-pointer
                   hover:bg-accent-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            @click="create"
            :disabled="!selectedTemplate"
          >Create</button>
        </div>
      </div>
    </div>
  </Teleport>
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
