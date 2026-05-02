<template>
  <Teleport to="body">
    <div class="fixed inset-0 bg-bg-overlay backdrop-blur-sm flex items-center justify-center z-50 p-4" @click.self="$emit('close')">
      <div class="bg-bg-secondary border border-border rounded-2xl w-full max-w-3xl flex flex-col shadow-2xl max-h-[88vh]">
        <div class="px-5 py-4 border-b border-border flex items-center justify-between">
          <div>
            <h2 class="text-lg font-semibold text-text-primary">Ask the Narrator</h2>
            <p class="text-xs text-text-muted mt-0.5">Analytical Q&A — the narrator has full context including masked intents and answers in plain prose, not narrative.</p>
          </div>
          <button class="text-text-muted hover:text-text-primary cursor-pointer" @click="$emit('close')">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="flex-1 overflow-y-auto px-5 py-4 space-y-4" ref="historyContainer">
          <div v-if="!history.length && !streaming" class="text-center text-text-muted italic py-8">
            <p>No questions yet. Ask anything about the story.</p>
            <p class="text-xs mt-2 opacity-70">Examples: "Is a marriage planned?" · "What's Tiffany's secret?" · "Where could this go next?"</p>
          </div>

          <div v-for="(qa, i) in history" :key="i" class="space-y-2">
            <div class="flex gap-2">
              <span class="text-accent text-sm font-semibold shrink-0">Q.</span>
              <p class="text-sm text-text-primary">{{ qa.question }}</p>
            </div>
            <details v-if="qa.thinking" class="ml-6">
              <summary class="text-xs text-text-muted cursor-pointer hover:text-text-secondary">💭 Thinking ({{ qa.thinking.length }} chars)</summary>
              <pre class="mt-2 p-2 text-xs text-text-muted whitespace-pre-wrap break-words font-ui leading-relaxed bg-bg-primary/40 rounded">{{ qa.thinking }}</pre>
            </details>
            <div class="ml-6 text-sm text-text-secondary whitespace-pre-wrap leading-relaxed">{{ qa.answer }}</div>
          </div>

          <!-- Live streaming Q&A -->
          <div v-if="streaming" class="space-y-2">
            <div class="flex gap-2">
              <span class="text-accent text-sm font-semibold shrink-0">Q.</span>
              <p class="text-sm text-text-primary">{{ pendingQuestion }}</p>
            </div>
            <div v-if="phase === 'thinking' || liveThinking" class="ml-6">
              <div class="text-xs text-purple-300 mb-1">💭 Thinking…</div>
              <pre class="p-2 text-xs text-text-muted whitespace-pre-wrap break-words font-ui leading-relaxed bg-bg-primary/40 rounded max-h-40 overflow-y-auto">{{ liveThinking }}<span v-if="phase === 'thinking'" class="inline-block w-1.5 h-3 bg-purple-400/60 align-middle animate-pulse"></span></pre>
            </div>
            <div v-if="phase === 'answer' || liveAnswer" class="ml-6 text-sm text-text-secondary whitespace-pre-wrap leading-relaxed">{{ liveAnswer }}<span v-if="phase === 'answer'" class="inline-block w-2 h-4 bg-accent/60 align-middle animate-pulse"></span></div>
            <div v-if="phase === 'preparing' || phase === 'loading_model'" class="ml-6 text-xs text-text-muted italic">
              <template v-if="phase === 'loading_model'">Loading model…</template>
              <template v-else>Preparing…</template>
            </div>
          </div>
        </div>

        <div class="px-5 py-3 border-t border-border bg-bg-surface/30">
          <form class="flex gap-2" @submit.prevent="ask">
            <textarea
              v-model="question"
              placeholder="Ask anything about the story…"
              :disabled="streaming"
              rows="1"
              ref="textarea"
              @keydown.enter.exact.prevent="ask"
              @input="autoResize"
              class="flex-1 px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors disabled:opacity-50 resize-none leading-relaxed"
            ></textarea>
            <button
              type="submit"
              class="px-4 py-2 bg-accent rounded-lg text-white text-sm font-semibold cursor-pointer
                     hover:bg-accent-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              :disabled="streaming || !question.trim()"
            >{{ streaming ? '...' : 'Ask' }}</button>
            <button
              v-if="streaming"
              type="button"
              class="px-3 py-2 border border-error/40 text-error rounded-lg hover:bg-error/10 transition-colors cursor-pointer"
              @click="cancel"
            >Stop</button>
          </form>
          <div v-if="error" class="mt-2 text-xs text-error">{{ error }}</div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, nextTick } from 'vue';
import { useRoute } from 'vue-router';
import * as queryApi from '../../api/query.js';

defineEmits(['close']);

const route = useRoute();
const sessionId = route.params.id;

const history = ref([]);             // [{question, thinking, answer}]
const question = ref('');
const pendingQuestion = ref('');
const liveThinking = ref('');
const liveAnswer = ref('');
const phase = ref('idle');           // 'idle' | 'preparing' | 'loading_model' | 'thinking' | 'answer' | 'done' | 'error'
const streaming = ref(false);
const error = ref('');
const textarea = ref(null);
const historyContainer = ref(null);
let abortCtrl = null;

function autoResize() {
  if (!textarea.value) return;
  textarea.value.style.height = 'auto';
  textarea.value.style.height = Math.min(textarea.value.scrollHeight, 120) + 'px';
}

function scrollToBottom() {
  nextTick(() => {
    if (historyContainer.value) {
      historyContainer.value.scrollTop = historyContainer.value.scrollHeight;
    }
  });
}

async function ask() {
  const q = question.value.trim();
  if (!q || streaming.value) return;

  streaming.value = true;
  error.value = '';
  pendingQuestion.value = q;
  liveThinking.value = '';
  liveAnswer.value = '';
  phase.value = 'preparing';
  question.value = '';
  nextTick(autoResize);
  scrollToBottom();

  abortCtrl = new AbortController();
  const histPayload = history.value.map(h => ({ question: h.question, answer: h.answer }));

  try {
    await queryApi.streamQuery(
      sessionId,
      { question: q, history: histPayload },
      handleEvent,
      abortCtrl.signal,
    );
  } catch (err) {
    if (err.name !== 'AbortError') {
      error.value = err.message || 'Query failed';
      phase.value = 'error';
    }
  } finally {
    streaming.value = false;
    abortCtrl = null;
    if (phase.value !== 'error' && (liveAnswer.value || liveThinking.value)) {
      history.value.push({
        question: pendingQuestion.value,
        thinking: liveThinking.value,
        answer: liveAnswer.value,
      });
    }
    pendingQuestion.value = '';
    liveThinking.value = '';
    liveAnswer.value = '';
    phase.value = 'idle';
    scrollToBottom();
  }
}

function handleEvent(ev) {
  switch (ev.type) {
    case 'model_loading':
      phase.value = 'loading_model';
      break;
    case 'model_loaded':
    case 'started':
      phase.value = 'thinking';
      break;
    case 'thinking_start':
      phase.value = 'thinking';
      liveThinking.value = '';
      break;
    case 'thinking_chunk':
      liveThinking.value += ev.text || '';
      break;
    case 'thinking_done':
      phase.value = 'answer';
      break;
    case 'answer_start':
      phase.value = 'answer';
      liveAnswer.value = '';
      break;
    case 'answer_chunk':
      liveAnswer.value += ev.text || '';
      scrollToBottom();
      break;
    case 'answer_done':
      phase.value = 'done';
      break;
    case 'done':
      // Final state already captured in liveThinking/liveAnswer
      break;
    case 'error':
      error.value = ev.message || 'error';
      phase.value = 'error';
      break;
  }
}

function cancel() {
  if (abortCtrl) abortCtrl.abort();
}
</script>
