<template>
  <div class="flex-1 max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-10 w-full">
    <div class="flex items-center justify-between mb-6">
      <h1 class="font-body text-2xl sm:text-3xl font-bold">LLM Activity</h1>
      <div class="flex items-center gap-3 text-xs text-text-muted">
        <span class="w-2 h-2 rounded-full" :class="polling ? 'bg-green-400 animate-pulse' : 'bg-text-muted/30'"></span>
        {{ polling ? 'Auto-refresh (1s)' : 'Stopped' }}
        <button
          class="px-2 py-1 border border-border rounded text-text-secondary hover:border-accent/40 hover:text-text-primary transition-all cursor-pointer"
          @click="polling = !polling"
        >{{ polling ? 'Pause' : 'Resume' }}</button>
      </div>
    </div>

    <!-- llama-server status -->
    <div class="mb-6 p-4 bg-bg-surface rounded-xl border border-border flex items-center gap-3">
      <span class="w-2.5 h-2.5 rounded-full" :class="llama.running ? 'bg-green-400' : 'bg-text-muted/30'"></span>
      <span class="text-sm text-text-secondary">
        llama-server: <span class="font-mono text-text-primary">{{ llama.running ? 'running' : 'stopped' }}</span>
      </span>
    </div>

    <!-- Active (queued + running) -->
    <div class="mb-6">
      <h2 class="font-body text-sm font-bold mb-3 uppercase tracking-wider text-text-secondary">
        In Flight <span class="text-text-muted font-normal">({{ active.length }})</span>
      </h2>
      <div v-if="!active.length" class="text-sm text-text-muted italic px-4 py-6 text-center bg-bg-surface/30 rounded-xl border border-border-subtle">
        No active calls.
      </div>
      <ul v-else class="flex flex-col gap-2">
        <li v-for="call in active" :key="call.id"
          class="flex flex-col gap-2 px-4 py-3 bg-bg-surface rounded-lg border"
          :class="call.status === 'running' ? 'border-accent/40' : 'border-border'">
          <div class="flex items-center gap-3">
            <span class="px-2 py-0.5 text-xs rounded font-mono uppercase"
              :class="call.status === 'running' ? 'bg-accent/20 text-accent' : 'bg-bg-primary text-text-muted'">
              {{ call.status }}
            </span>
            <span class="font-mono text-sm text-text-primary">{{ call.kind }}</span>
            <span v-if="call.session_id" class="text-xs text-text-muted font-mono truncate max-w-[200px]" :title="call.session_id">
              {{ call.session_id.slice(0, 8) }}
            </span>
            <span class="ml-auto text-xs text-text-muted tabular-nums">
              {{ elapsed(call) }}
            </span>
            <button
              v-if="call.request_file"
              class="px-2 py-0.5 text-xs text-accent hover:underline cursor-pointer"
              @click="openDump(call.request_file, 'request')"
              title="View the request sent to the model"
            >query</button>
            <button
              class="px-2 py-0.5 text-xs border border-error/40 text-error rounded hover:bg-error/10 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              :disabled="cancelling.has(call.id)"
              @click="cancelOne(call.id)"
              title="Cancel this call"
            >{{ cancelling.has(call.id) ? 'Cancelling…' : 'Cancel' }}</button>
          </div>
          <!-- Live metrics from the SSE reader (filled when running) -->
          <div v-if="call.status === 'running'" class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div class="flex flex-col gap-0.5">
              <span class="text-text-muted uppercase">Generated</span>
              <span class="font-mono text-text-secondary tabular-nums">
                {{ call.completion_tokens ?? 0 }} tok
              </span>
            </div>
            <div v-if="call.thinking_tokens != null || call.narrative_tokens != null"
              class="flex flex-col gap-0.5">
              <span class="text-text-muted uppercase">Think / Narr</span>
              <span class="font-mono text-text-secondary tabular-nums">
                {{ call.thinking_tokens ?? 0 }} / {{ call.narrative_tokens ?? 0 }}
              </span>
            </div>
            <div class="flex flex-col gap-0.5">
              <span class="text-text-muted uppercase">Speed</span>
              <span class="font-mono text-text-secondary tabular-nums">
                {{ call.tokens_per_sec != null ? call.tokens_per_sec.toFixed(1) + ' tok/s' : '—' }}
              </span>
            </div>
            <div class="flex flex-col gap-0.5">
              <span class="text-text-muted uppercase">TTFT</span>
              <span class="font-mono text-text-secondary tabular-nums">
                {{ call.first_token_ms != null ? formatMs(call.first_token_ms) : '—' }}
              </span>
            </div>
          </div>
        </li>
      </ul>
    </div>

    <!-- History -->
    <div class="mb-6">
      <h2 class="font-body text-sm font-bold mb-3 uppercase tracking-wider text-text-secondary">
        Recent Calls <span class="text-text-muted font-normal">(last {{ history.length }})</span>
      </h2>
      <div v-if="!history.length" class="text-sm text-text-muted italic px-4 py-6 text-center bg-bg-surface/30 rounded-xl border border-border-subtle">
        No history yet.
      </div>
      <div v-else class="overflow-x-auto rounded-xl border border-border-subtle">
        <table class="w-full text-sm">
          <thead class="bg-bg-surface text-xs text-text-muted uppercase">
            <tr>
              <th class="px-3 py-2 text-left font-medium">When</th>
              <th class="px-3 py-2 text-left font-medium">Kind</th>
              <th class="px-3 py-2 text-left font-medium">Status</th>
              <th class="px-3 py-2 text-right font-medium">Duration</th>
              <th class="px-3 py-2 text-right font-medium">TTFT</th>
              <th class="px-3 py-2 text-right font-medium">Prompt</th>
              <th class="px-3 py-2 text-right font-medium">Gen</th>
              <th class="px-3 py-2 text-right font-medium">Tok/s</th>
              <th class="px-3 py-2 text-right font-medium">Cost</th>
              <th class="px-3 py-2 text-left font-medium">Model</th>
              <th class="px-3 py-2 text-left font-medium">Inspect</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(call, idx) in history" :key="idx"
              class="border-t border-border-subtle hover:bg-bg-surface/30 transition-colors">
              <td class="px-3 py-2 text-xs text-text-muted tabular-nums">{{ ago(call.ended_at) }}</td>
              <td class="px-3 py-2 font-mono text-xs">{{ call.kind }}</td>
              <td class="px-3 py-2">
                <span class="px-1.5 py-0.5 text-xs rounded font-mono"
                  :class="call.status === 'success' ? 'bg-green-500/15 text-green-400' : 'bg-error/15 text-error'"
                  :title="call.error || ''">
                  {{ call.status }}
                </span>
              </td>
              <td class="px-3 py-2 text-right text-xs text-text-secondary tabular-nums">{{ formatMs(call.duration_ms) }}</td>
              <td class="px-3 py-2 text-right text-xs text-text-muted tabular-nums">{{ call.first_token_ms != null ? formatMs(call.first_token_ms) : '—' }}</td>
              <td class="px-3 py-2 text-right text-xs text-text-muted tabular-nums">{{ call.prompt_tokens ?? '—' }}</td>
              <td class="px-3 py-2 text-right text-xs text-text-muted tabular-nums">{{ call.completion_tokens ?? '—' }}</td>
              <td class="px-3 py-2 text-right text-xs text-text-muted tabular-nums">{{ histToksPerSec(call) }}</td>
              <td class="px-3 py-2 text-right text-xs tabular-nums"
                :class="call.cost_in_usd_ticks ? 'text-text-secondary' : 'text-text-muted'"
                :title="call.cost_in_usd_ticks ? `${call.cost_in_usd_ticks.toLocaleString()} ticks` : ''">
                {{ formatCost(call.cost_in_usd_ticks) }}
              </td>
              <td class="px-3 py-2 text-xs text-text-muted font-mono truncate max-w-[160px]" :title="call.model">{{ shortModel(call.model) }}</td>
              <td class="px-3 py-2 text-xs">
                <div class="flex gap-2">
                  <button
                    v-if="call.request_file"
                    class="text-accent hover:underline cursor-pointer"
                    @click="openDump(call.request_file, 'request')"
                    title="View the request sent to llama-server (messages, samplers, grammar)"
                  >query</button>
                  <button
                    v-if="call.dump_file"
                    class="text-accent hover:underline cursor-pointer"
                    @click="openDump(call.dump_file, 'response')"
                    title="View the raw response from the model"
                  >response</button>
                  <span v-if="!call.dump_file && !call.request_file" class="text-text-muted">—</span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Dump viewer modal -->
    <Teleport to="body">
      <div v-if="dumpOpen" class="fixed inset-0 bg-bg-overlay backdrop-blur-sm flex items-center justify-center z-50 p-4" @click.self="dumpOpen = false">
        <div class="bg-bg-secondary border border-border rounded-2xl w-full max-w-4xl flex flex-col shadow-2xl max-h-[85vh]">
          <div class="flex items-center justify-between px-5 py-3 border-b border-border">
            <h2 class="text-sm font-mono text-text-primary truncate">{{ dumpName }}</h2>
            <button class="text-text-muted hover:text-text-primary cursor-pointer" @click="dumpOpen = false">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <pre class="flex-1 overflow-auto p-4 text-xs font-mono text-text-secondary whitespace-pre-wrap break-words bg-bg-primary">{{ dumpContent || 'Loading…' }}</pre>
          <div class="px-5 py-2 border-t border-border text-xs text-text-muted">{{ dumpContent.length }} chars</div>
        </div>
      </div>
    </Teleport>

    <!-- llama-server logs (collapsible, polled only when open) -->
    <div class="rounded-xl border border-border-subtle overflow-hidden">
      <button
        class="w-full px-4 py-3 bg-bg-surface flex items-center justify-between text-left cursor-pointer hover:bg-bg-surface/70 transition-colors"
        @click="logsOpen = !logsOpen"
      >
        <span class="font-body text-sm font-bold uppercase tracking-wider text-text-secondary">
          llama-server logs
          <span class="text-text-muted font-normal normal-case ml-2">{{ logsOpen ? '(polling every 2s)' : '(click to open)' }}</span>
        </span>
        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 transition-transform" :class="logsOpen ? 'rotate-180' : ''" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      <div v-if="logsOpen" class="bg-bg-primary max-h-96 overflow-y-auto p-3 text-xs font-mono text-text-secondary" ref="logContainer">
        <div v-if="!logLines.length" class="text-text-muted italic text-center py-6">No logs captured yet (load a model first).</div>
        <pre v-else class="whitespace-pre-wrap break-words leading-relaxed">{{ logText }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue';
import * as llmApi from '../api/llm.js';

const active = ref([]);
const history = ref([]);
const llama = ref({ running: false });
const polling = ref(true);
const now = ref(Date.now());

const logsOpen = ref(false);
const logLines = ref([]);
const logContainer = ref(null);

const dumpOpen = ref(false);
const dumpName = ref('');
const dumpContent = ref('');

const cancelling = ref(new Set());

async function cancelOne(id) {
  cancelling.value.add(id);
  try {
    await llmApi.cancelCall(id);
  } catch { /* call may have already finished */ }
  // Force a tick refresh to show the new status quickly
  setTimeout(() => {
    cancelling.value.delete(id);
    tickActivity();
  }, 800);
}

async function openDump(filename, kind = 'response') {
  dumpName.value = `${kind}: ${filename}`;
  dumpContent.value = '';
  dumpOpen.value = true;
  try {
    const fetcher = kind === 'request' ? llmApi.getRequestDump : llmApi.getResponseDump;
    const res = await fetcher(filename);
    dumpContent.value = res.content || '';
  } catch (err) {
    dumpContent.value = `Failed to load: ${err?.message || 'unknown error'}`;
  }
}

let activityTimer = null;
let clockTimer = null;
let logsTimer = null;
let activityInFlight = false;
let logsInFlight = false;

const logText = computed(() => logLines.value.join('\n'));

async function tickActivity() {
  if (activityInFlight || !polling.value) return;
  activityInFlight = true;
  try {
    const snap = await llmApi.getActivity();
    active.value = snap.active || [];
    history.value = snap.history || [];
    llama.value = snap.llamaServer || { running: false };
  } catch { /* ignore */ } finally {
    activityInFlight = false;
  }
}

async function tickLogs() {
  if (!logsOpen.value || logsInFlight) return;
  logsInFlight = true;
  try {
    const res = await llmApi.getLogs(400);
    const wasAtBottom = logContainer.value
      && (logContainer.value.scrollHeight - logContainer.value.scrollTop - logContainer.value.clientHeight < 40);
    logLines.value = res.lines || [];
    if (wasAtBottom) {
      nextTick(() => {
        if (logContainer.value) logContainer.value.scrollTop = logContainer.value.scrollHeight;
      });
    }
  } catch { /* ignore */ } finally {
    logsInFlight = false;
  }
}

watch(logsOpen, (open) => {
  if (open) tickLogs();
});

onMounted(() => {
  tickActivity();
  activityTimer = setInterval(tickActivity, 1000);
  clockTimer = setInterval(() => {
    if (active.value.length) now.value = Date.now();
  }, 500);
  logsTimer = setInterval(tickLogs, 2000);
});

onUnmounted(() => {
  clearInterval(activityTimer);
  clearInterval(clockTimer);
  clearInterval(logsTimer);
});

function elapsed(call) {
  const start = call.running_at || call.started_at;
  const seconds = Math.max(0, now.value / 1000 - start);
  if (seconds < 60) return seconds.toFixed(1) + 's';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}m ${s}s`;
}

function ago(unix) {
  if (!unix) return '—';
  const diff = Math.max(0, now.value / 1000 - unix);
  if (diff < 60) return Math.floor(diff) + 's ago';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  return Math.floor(diff / 3600) + 'h ago';
}

function formatMs(ms) {
  if (ms == null) return '—';
  if (ms < 1000) return ms + 'ms';
  return (ms / 1000).toFixed(1) + 's';
}

function histToksPerSec(call) {
  if (call.tokens_per_sec != null) return call.tokens_per_sec.toFixed(1);
  if (!call.completion_tokens || !call.duration_ms) return '—';
  return ((call.completion_tokens / call.duration_ms) * 1000).toFixed(1);
}

function shortModel(name) {
  if (!name) return '—';
  return name.split(/[\\/]/).pop();
}

function formatCost(ticks) {
  if (ticks == null) return '—';
  return '$' + (ticks / 10_000_000_000).toFixed(4);
}
</script>
