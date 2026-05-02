<template>
  <div
    v-if="visibleJobs.length"
    class="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm pointer-events-none"
  >
    <div
      v-for="job in visibleJobs"
      :key="job.id"
      class="pointer-events-auto bg-bg-surface border border-border-subtle rounded-xl shadow-lg overflow-hidden"
    >
      <div class="px-4 py-3 flex items-start gap-3">
        <!-- Status icon -->
        <div class="shrink-0 mt-0.5">
          <svg v-if="job.status === 'running'" class="w-4 h-4 text-accent animate-spin" fill="none" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-opacity="0.3" stroke-width="3" />
            <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
          </svg>
          <svg v-else-if="job.status === 'queued'" class="w-4 h-4 text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>

        <div class="flex-1 min-w-0">
          <div class="flex items-baseline gap-2">
            <span
              class="text-[10px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded"
              :class="kindBadgeClass(job.kind)"
            >{{ kindLabel(job.kind) }}</span>
            <span v-if="job.status === 'queued'" class="text-xs text-text-muted">
              queued{{ job.queuePosition > 0 ? ` · ${job.queuePosition} ahead` : '' }}
            </span>
            <span v-else-if="liveStatsByJob[job.id]" class="text-xs text-text-muted tabular-nums">
              {{ liveStatsByJob[job.id].tokens }} tok · {{ liveStatsByJob[job.id].rate.toFixed(1) }}/s
            </span>
          </div>
          <div class="text-sm text-text-primary truncate" :title="job.label">
            {{ job.label }}
          </div>
        </div>

        <button
          class="shrink-0 text-xs px-2 py-0.5 border border-error/40 text-error rounded hover:bg-error/10 transition-colors cursor-pointer"
          @click="store.cancel(job.id)"
          title="Cancel"
        >Stop</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, watch, onUnmounted, reactive } from 'vue';
import { useJobsStore } from '../../stores/jobs.js';
import * as jobsApi from '../../api/jobs.js';

const store = useJobsStore();

// Narrative + regenerate already have a dedicated streaming UI in SessionView,
// so they don't need a duplicate toast. Everything else is "background work" —
// toast it.
const HIDDEN_KINDS = new Set(['narrative', 'regenerate']);

const visibleJobs = computed(() =>
  store.active.filter(j => !HIDDEN_KINDS.has(j.kind))
);

const KIND_LABELS = {
  'chub-import': 'Import',
  'rerun': 'Rerun',
  'enrich': 'Enrich',
  'meta': 'Meta',
  'consolidate': 'Consolidate',
  'title': 'Title',
  'finalize-chapter': 'Finalize',
};
function kindLabel(kind) {
  return KIND_LABELS[kind] || kind;
}

const KIND_BADGE = {
  'chub-import': 'bg-accent/15 text-accent',
  'rerun': 'bg-purple-500/15 text-purple-300',
  'enrich': 'bg-purple-500/15 text-purple-300',
  'meta': 'bg-purple-500/15 text-purple-300',
  'consolidate': 'bg-purple-500/15 text-purple-300',
  'title': 'bg-emerald-500/15 text-emerald-300',
  'finalize-chapter': 'bg-emerald-500/15 text-emerald-300',
};
function kindBadgeClass(kind) {
  return KIND_BADGE[kind] || 'bg-bg-secondary text-text-secondary';
}

// Per-running-job live token stats. We attach an EventSource to each running
// job to get token deltas, count them, and show tokens/sec. The job's own
// SSE closes when the job terminates.
const liveStatsByJob = reactive({});
const sources = new Map();

function attachLive(job) {
  if (sources.has(job.id)) return;
  const startTs = performance.now();
  let firstTokenTs = null;
  let tokens = 0;
  liveStatsByJob[job.id] = { tokens: 0, rate: 0 };

  const es = jobsApi.subscribeToJob(job.id, (ev) => {
    if (ev.type === 'first_token') {
      firstTokenTs = performance.now();
    } else if (ev.type === 'delta') {
      tokens++;
      const elapsed = (firstTokenTs ? performance.now() - firstTokenTs : performance.now() - startTs) / 1000;
      const rate = elapsed > 0.1 ? tokens / elapsed : 0;
      liveStatsByJob[job.id] = { tokens, rate };
    }
  }, () => {
    sources.delete(job.id);
  });
  sources.set(job.id, es);
}

function detachLive(jobId) {
  const es = sources.get(jobId);
  if (es) {
    es.close();
    sources.delete(jobId);
  }
  delete liveStatsByJob[jobId];
}

watch(visibleJobs, (jobs) => {
  const seen = new Set(jobs.map(j => j.id));
  // Attach for jobs that just transitioned to running.
  for (const job of jobs) {
    if (job.status === 'running' && !sources.has(job.id)) {
      attachLive(job);
    }
  }
  // Detach for jobs that left the visible list.
  for (const id of [...sources.keys()]) {
    if (!seen.has(id)) detachLive(id);
  }
}, { immediate: true });

onUnmounted(() => {
  for (const es of sources.values()) es.close();
  sources.clear();
});
</script>
