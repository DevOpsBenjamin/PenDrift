<template>
  <Teleport to="body">
    <div class="fixed inset-0 bg-bg-overlay backdrop-blur-sm flex items-center justify-center z-50 p-4" @click.self="$emit('close')">
      <div class="bg-bg-secondary border border-border rounded-2xl w-full max-w-2xl max-h-[80vh] flex flex-col shadow-2xl">
        <div class="flex items-center justify-between p-5 border-b border-border-subtle">
          <div class="flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            <h2 class="text-lg font-semibold">Model Reasoning</h2>
          </div>
          <button
            class="text-text-muted hover:text-text-primary transition-colors p-1"
            @click="$emit('close')"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="flex-1 overflow-y-auto p-5 prose-thinking" v-html="renderedThinking"></div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed } from 'vue';
import MarkdownIt from 'markdown-it';

const props = defineProps({ thinking: String });
defineEmits(['close']);

const md = new MarkdownIt({ html: false, breaks: true });

const renderedThinking = computed(() => {
  if (!props.thinking) return '';
  return md.render(props.thinking);
});
</script>

<style>
.prose-thinking {
  font-family: var(--font-ui);
  font-size: 0.85rem;
  line-height: 1.7;
  color: var(--color-text-secondary);
}

.prose-thinking h1, .prose-thinking h2, .prose-thinking h3, .prose-thinking h4 {
  color: var(--color-text-primary);
  font-weight: 600;
  margin-top: 1rem;
  margin-bottom: 0.5rem;
}

.prose-thinking h1 { font-size: 1.1rem; }
.prose-thinking h2 { font-size: 1rem; }
.prose-thinking h3 { font-size: 0.9rem; }

.prose-thinking p {
  margin-bottom: 0.6rem;
}

.prose-thinking ul, .prose-thinking ol {
  padding-left: 1.5rem;
  margin-bottom: 0.6rem;
}

.prose-thinking li {
  margin-bottom: 0.3rem;
}

.prose-thinking strong {
  color: var(--color-text-primary);
}

.prose-thinking em {
  color: var(--color-accent);
  font-style: italic;
}

.prose-thinking code {
  background: var(--color-bg-surface);
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  font-size: 0.8rem;
}

.prose-thinking blockquote {
  border-left: 2px solid var(--color-border);
  padding-left: 0.75rem;
  margin-left: 0;
  color: var(--color-text-muted);
}
</style>
