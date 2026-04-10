<template>
  <div class="p-3 sm:p-4 border-t border-border-subtle bg-bg-secondary/80 backdrop-blur-sm">
    <div class="max-w-2xl mx-auto">
      <div class="flex gap-2 sm:gap-3 items-end">
        <!-- Generating spinner -->
        <div v-if="generating" class="flex items-center justify-center w-8 h-8 shrink-0 mb-0.5">
          <div class="w-5 h-5 border-2 border-accent/30 border-t-accent rounded-full animate-spin"></div>
        </div>
        <textarea
          ref="textarea"
          v-model="directive"
          placeholder="Write your directive..."
          :disabled="generating"
          @keydown.enter.exact="submit"
          @input="autoResize"
          rows="1"
          class="flex-1 px-3 sm:px-4 py-2.5 bg-bg-primary border border-border rounded-xl text-text-primary
                 text-sm sm:text-base placeholder:text-text-muted resize-none leading-relaxed
                 focus:outline-none focus:border-accent/60 focus:ring-1 focus:ring-accent/20
                 disabled:opacity-40 transition-all overflow-hidden"
        ></textarea>
        <button
          class="px-4 sm:px-6 py-2.5 bg-accent rounded-xl text-white text-sm font-semibold cursor-pointer
                 whitespace-nowrap hover:bg-accent-hover active:scale-95 transition-all
                 disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100"
          @click="submit"
          :disabled="generating || !directive.trim()"
        >
          <span class="hidden sm:inline">{{ generating ? 'Generating...' : 'Generate' }}</span>
          <span class="sm:hidden">{{ generating ? '...' : 'Go' }}</span>
        </button>
      </div>
      <div class="flex justify-between items-center mt-2 text-xs text-text-muted">
        <label class="flex items-center gap-1.5 cursor-pointer select-none hover:text-text-secondary transition-colors">
          <input
            type="checkbox"
            v-model="isKeyMoment"
            class="accent-accent w-3.5 h-3.5"
          />
          Key moment
        </label>
        <span class="hidden sm:inline opacity-50">Enter to send, Shift+Enter for newline</span>
      </div>
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
