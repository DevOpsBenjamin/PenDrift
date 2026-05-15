<template>
  <Teleport to="body">
    <div class="fixed inset-0 bg-bg-overlay backdrop-blur-sm flex items-center justify-center z-50 p-4" @click.self="$emit('close')">
      <div class="bg-bg-secondary border border-border rounded-2xl w-full max-w-3xl flex flex-col shadow-2xl max-h-[88vh]">
        <div class="px-5 py-4 border-b border-border flex items-center justify-between">
          <div>
            <h2 class="text-lg font-semibold text-text-primary">Ask the Template</h2>
            <p class="text-xs text-text-muted mt-0.5">
              Meta-analytical Q&A — the model reads the template and answers about its structure, goals, hidden mechanics, encoded references, and what's missing.
              <span v-if="sessionId" class="text-amber-300/80">Session evidence attached.</span>
            </p>
          </div>
          <button class="text-text-muted hover:text-text-primary cursor-pointer" @click="$emit('close')">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="flex-1 overflow-y-auto px-5 py-4 space-y-4" ref="historyContainer">
          <div v-if="!history.length && !streaming" class="text-center text-text-muted italic py-8">
            <p>No questions yet. Ask anything about this template.</p>
            <p class="text-xs mt-2 opacity-70">
              Examples: "What is this template trying to do?" · "Why is the story stuck on shell-collecting?" · "What's coded that I should make explicit?" · "What milestones is this template missing?"
            </p>
          </div>

          <div v-for="(qa, i) in history" :key="qa.id ?? i" class="space-y-2">
            <div class="flex gap-2 items-baseline">
              <span class="text-purple-300 text-sm font-semibold shrink-0">Q.</span>
              <p class="text-sm text-text-primary flex-1">{{ qa.question }}</p>
              <span
                v-if="qa.status && qa.status !== 'success'"
                class="text-[10px] uppercase tracking-wider font-mono px-1.5 py-0.5 rounded shrink-0"
                :class="{
                  'bg-amber-500/15 text-amber-300': qa.status === 'running',
                  'bg-text-muted/15 text-text-muted': qa.status === 'cancelled',
                  'bg-error/15 text-error': qa.status === 'error',
                }"
              >{{ qa.status }}</span>
            </div>
            <details v-if="qa.thinking" class="ml-6">
              <summary class="text-xs text-text-muted cursor-pointer hover:text-text-secondary">💭 Thinking ({{ qa.thinking.length }} chars)</summary>
              <pre class="mt-2 p-2 text-xs text-text-muted whitespace-pre-wrap break-words font-ui leading-relaxed bg-bg-primary/40 rounded">{{ qa.thinking }}</pre>
            </details>
            <details v-if="qa.answer" class="ml-6">
              <summary class="text-xs text-purple-300/80 cursor-pointer hover:text-purple-300 select-none">
                📖 Answer ({{ qa.answer.length }} chars) <span class="text-text-muted">— {{ qa.answer.slice(0, 90).replace(/\s+/g, ' ').trim() }}…</span>
              </summary>
              <div class="mt-2 text-sm text-text-secondary whitespace-pre-wrap leading-relaxed">{{ qa.answer }}</div>
            </details>
            <div v-else-if="qa.status === 'running'" class="ml-6 text-xs text-amber-300/80 italic">
              Still processing in background — close and reopen the modal to refresh.
            </div>
            <div v-else-if="qa.status === 'cancelled' && !qa.answer" class="ml-6 text-xs text-text-muted italic">
              Cancelled before any answer was produced.
            </div>
            <div v-else-if="qa.status === 'error'" class="ml-6 text-xs text-error italic">
              Failed: {{ qa.error || 'unknown error' }}
            </div>
          </div>

          <!-- Live streaming Q&A -->
          <div v-if="streaming" class="space-y-2">
            <div class="flex gap-2">
              <span class="text-purple-300 text-sm font-semibold shrink-0">Q.</span>
              <p class="text-sm text-text-primary">{{ pendingQuestion }}</p>
            </div>
            <div v-if="phase === 'thinking' || liveThinking" class="ml-6">
              <div class="text-xs text-purple-300 mb-1">💭 Thinking…</div>
              <pre class="p-2 text-xs text-text-muted whitespace-pre-wrap break-words font-ui leading-relaxed bg-bg-primary/40 rounded max-h-40 overflow-y-auto">{{ liveThinking }}<span v-if="phase === 'thinking'" class="inline-block w-1.5 h-3 bg-purple-400/60 align-middle animate-pulse"></span></pre>
            </div>
            <div v-if="phase === 'answer' || liveAnswer" class="ml-6 text-sm text-text-secondary whitespace-pre-wrap leading-relaxed">{{ liveAnswer }}<span v-if="phase === 'answer'" class="inline-block w-2 h-4 bg-purple-400/60 align-middle animate-pulse"></span></div>
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
              :placeholder="sessionId ? 'Ask about this template — session attached as evidence…' : 'Ask about this template…'"
              :disabled="streaming"
              rows="1"
              ref="textarea"
              @keydown.enter.exact.prevent="ask"
              @input="autoResize"
              class="flex-1 px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-purple-400 transition-colors disabled:opacity-50 resize-none leading-relaxed"
            ></textarea>
            <button
              type="submit"
              class="px-4 py-2 bg-purple-500 rounded-lg text-white text-sm font-semibold cursor-pointer
                     hover:bg-purple-400 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
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
import { ref, nextTick, onMounted } from 'vue';
import * as templateQueryApi from '../../api/templateQuery.js';

const props = defineProps({
  templateId: { type: String, required: true },
  // When set, the backend attaches the session's recent chunks + asks as
  // evidence of "what this template actually produced". Useful for diagnosing
  // why a session is stuck.
  sessionId: { type: String, default: null },
});
defineEmits(['close']);

const history = ref([]);
const question = ref('');
const pendingQuestion = ref('');
const liveThinking = ref('');
const liveAnswer = ref('');
const phase = ref('idle');
const streaming = ref(false);
const error = ref('');
const textarea = ref(null);
const historyContainer = ref(null);
let abortCtrl = null;

onMounted(async () => {
  try {
    const res = await templateQueryApi.getTemplateQueries(props.templateId);
    history.value = (res.queries || []).map(q => ({
      id: q.id,
      question: q.question,
      thinking: q.thinking || '',
      answer: q.answer || '',
      status: q.status,
      error: q.error,
    }));
    scrollToBottom();
  } catch (err) {
    error.value = `Could not load past queries: ${err.message}`;
  }
});

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
  try {
    await templateQueryApi.streamTemplateQuery(
      props.templateId,
      { question: q, sessionId: props.sessionId },
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
        status: 'success',
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
    case 'model_loading': phase.value = 'loading_model'; break;
    case 'model_loaded':
    case 'started': phase.value = 'thinking'; break;
    case 'thinking_start':
      phase.value = 'thinking';
      liveThinking.value = '';
      break;
    case 'thinking_chunk': liveThinking.value += ev.text || ''; break;
    case 'thinking_done': phase.value = 'answer'; break;
    case 'answer_start':
      phase.value = 'answer';
      liveAnswer.value = '';
      break;
    case 'answer_chunk':
      liveAnswer.value += ev.text || '';
      scrollToBottom();
      break;
    case 'answer_done': phase.value = 'done'; break;
    case 'done': break;
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
