<template>
  <Teleport to="body">
    <div class="fixed inset-0 bg-bg-overlay backdrop-blur-sm flex items-center justify-center z-50 p-4" @click.self="$emit('close')">
      <div class="bg-bg-secondary border border-border rounded-2xl w-full max-w-lg max-h-[80vh] flex flex-col shadow-2xl">
        <div class="flex items-center justify-between p-5 border-b border-border-subtle">
          <h2 class="text-lg font-semibold">Established Facts</h2>
          <button class="text-text-muted hover:text-text-primary transition-colors p-1" @click="$emit('close')">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="flex-1 overflow-y-auto p-5">
          <p class="text-xs text-text-muted mb-3">These facts are injected into the system prompt. Edit, add, or remove as needed. One fact per line.</p>
          <textarea
            v-model="factsText"
            rows="15"
            class="w-full px-3 py-2.5 bg-bg-primary border border-border rounded-lg text-sm text-text-primary
                   resize-y focus:outline-none focus:border-accent transition-colors leading-relaxed"
          ></textarea>
        </div>

        <div class="flex justify-end gap-3 p-5 border-t border-border-subtle">
          <button
            class="px-4 py-2 border border-border rounded-lg text-text-secondary text-sm
                   hover:bg-bg-surface hover:text-text-primary transition-all cursor-pointer"
            @click="$emit('close')"
          >Cancel</button>
          <button
            class="px-5 py-2 bg-accent rounded-lg text-white text-sm font-semibold
                   hover:bg-accent-hover transition-colors cursor-pointer"
            @click="save"
          >Save</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref } from 'vue';

const props = defineProps({ facts: Array });
const emit = defineEmits(['close', 'save']);

const factsText = ref((props.facts || []).join('\n'));

function save() {
  const facts = factsText.value.split('\n').map(s => s.trim()).filter(Boolean);
  emit('save', facts);
}
</script>
