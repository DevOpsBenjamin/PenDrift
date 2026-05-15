<template>
  <Teleport to="body">
    <div class="fixed inset-0 bg-bg-overlay backdrop-blur-sm flex items-center justify-center z-50 p-4" @click.self="onCloseRequest">
      <div class="bg-bg-secondary border border-border rounded-2xl w-full max-w-2xl flex flex-col shadow-2xl max-h-[88vh]">
        <div class="px-5 py-4 border-b border-border flex items-center justify-between">
          <div>
            <h2 class="text-lg font-semibold text-text-primary">Rewrite Template</h2>
            <p class="text-xs text-text-muted mt-0.5">
              Produces a new version using your feedback and any selected diagnostic asks. The current JSON isn't shown — only your inputs are. The new version lands as <code>{{ nextVersionLabel }}</code> on disk; existing sessions stay pinned to their current version unless you switch them manually.
            </p>
          </div>
          <button class="text-text-muted hover:text-text-primary cursor-pointer" :disabled="streaming" @click="onCloseRequest">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          <!-- Feedback textarea -->
          <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-text-muted mb-2">
              What to change
            </label>
            <textarea
              v-model="feedback"
              :disabled="streaming"
              rows="5"
              placeholder="e.g. Make it less slow-burn. Add 6-8 dated milestones (Day 1 to Day 7) with one concrete beat per day. Name any coded references explicitly so the model stops dancing around them. Drop the 'slow-burn pacing' clause and replace with 'one concrete beat per day'."
              class="w-full px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-purple-400 transition-colors disabled:opacity-50 leading-relaxed"
            ></textarea>
            <p class="mt-1 text-[11px] text-text-muted">
              Be specific. Concrete instructions ("add daily milestones", "name the Spade code", "drop slow-burn clause") produce better rewrites than vague ones ("make it better").
            </p>
          </div>

          <!-- Diagnostic asks -->
          <div v-if="asks.length || loadingAsks">
            <label class="block text-xs font-semibold uppercase tracking-wider text-text-muted mb-2">
              Diagnostic asks to include
              <span class="font-normal normal-case text-text-muted/70">— optional, from "Ask the Template"</span>
            </label>
            <div v-if="loadingAsks" class="text-xs text-text-muted italic">Loading asks…</div>
            <ul v-else class="space-y-1.5 max-h-64 overflow-y-auto pr-1">
              <li
                v-for="qa in asks"
                :key="qa.id"
                class="flex items-start gap-2 px-3 py-2 bg-bg-primary/40 border border-border-subtle rounded-lg
                       hover:border-border transition-colors"
              >
                <input
                  type="checkbox"
                  :id="`ask-${qa.id}`"
                  :value="qa.id"
                  v-model="selectedAskIds"
                  :disabled="streaming"
                  class="mt-1 shrink-0 cursor-pointer"
                />
                <label :for="`ask-${qa.id}`" class="flex-1 min-w-0 cursor-pointer">
                  <div class="text-xs text-text-primary truncate">{{ qa.question }}</div>
                  <div class="text-[11px] text-text-muted truncate mt-0.5">{{ previewAnswer(qa.answer) }}</div>
                </label>
              </li>
            </ul>
            <div v-if="!loadingAsks && asks.length" class="mt-2 flex items-center gap-3 text-[11px]">
              <button class="text-purple-300 hover:underline cursor-pointer" :disabled="streaming" @click="selectAllAsks">Select all</button>
              <button class="text-text-muted hover:text-text-secondary cursor-pointer" :disabled="streaming" @click="selectedAskIds = []">Clear</button>
              <span class="text-text-muted">{{ selectedAskIds.length }} of {{ asks.length }} selected</span>
            </div>
          </div>
          <div v-else class="text-xs text-text-muted italic px-1">
            No diagnostic asks yet. Use "Ask the Template" first if you want to surface gaps before rewriting.
          </div>

        </div>

        <div class="px-5 py-3 border-t border-border bg-bg-surface/30 flex items-center justify-between gap-2">
          <span class="text-[11px] text-text-muted">
            {{ feedback.trim().length }} chars in feedback · {{ selectedAskIds.length }} asks attached
          </span>
          <div class="flex gap-2">
            <button
              type="button"
              class="px-3 py-2 text-xs text-text-muted hover:text-text-secondary cursor-pointer"
              @click="onCloseRequest"
            >Cancel</button>
            <button
              type="button"
              class="px-4 py-2 bg-purple-500 rounded-lg text-white text-sm font-semibold cursor-pointer
                     hover:bg-purple-400 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              :disabled="!feedback.trim()"
              @click="submit"
              title="Starts the rewrite as a background job and closes this modal. Watch the toast bar in the header for progress; the new version lands on disk when done."
            >Rewrite (run in background)</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import * as templateQueryApi from '../../api/templateQuery.js';

const props = defineProps({
  templateId: { type: String, required: true },
  // Most-recent existing version, e.g. "0001". Used only to display
  // "next version is 0002" in the header — the backend computes the actual
  // next number on save.
  currentVersion: { type: String, default: null },
});
const emit = defineEmits(['close', 'done']);

const feedback = ref('');
const asks = ref([]);
const selectedAskIds = ref([]);
const loadingAsks = ref(true);

const nextVersionLabel = computed(() => {
  if (!props.currentVersion) return 'next version';
  const n = parseInt(props.currentVersion, 10);
  if (Number.isNaN(n)) return 'next version';
  return String(n + 1).padStart(4, '0');
});

onMounted(async () => {
  try {
    const res = await templateQueryApi.getTemplateQueries(props.templateId);
    asks.value = (res.queries || []).filter(q => q.status === 'success' && q.answer);
  } catch {
    asks.value = [];
  } finally {
    loadingAsks.value = false;
  }
});

function previewAnswer(answer) {
  if (!answer) return '';
  return answer.slice(0, 120).replace(/\s+/g, ' ').trim() + (answer.length > 120 ? '…' : '');
}

function selectAllAsks() {
  selectedAskIds.value = asks.value.map(q => q.id);
}

function onCloseRequest() {
  emit('close');
}

function submit() {
  if (!feedback.value.trim()) return;
  // Fire-and-forget: the rewrite is a Job on the backend (job_manager) so it
  // survives client disconnect — we don't need to keep the modal open or
  // hold the SSE connection. The toast bar in the header shows progress via
  // the global jobs store; the new version lands on disk regardless.
  templateQueryApi.streamTemplateRewrite(
    props.templateId,
    { feedback: feedback.value.trim(), askIds: selectedAskIds.value },
    () => { /* ignore events client-side; job persists results to disk */ },
  ).catch(() => { /* job survives any client error; surfaced via toast */ });
  emit('done', { started: true });
  emit('close');
}
</script>
