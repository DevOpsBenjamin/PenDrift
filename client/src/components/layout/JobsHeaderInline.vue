<template>
  <div v-if="visibleJobs.length" class="flex items-center gap-2">
    <div
      class="flex items-center gap-2 px-2.5 py-1.5 bg-bg-surface/70 border border-border-subtle rounded-lg"
    >
      <svg v-if="primary.status === 'running'" class="w-3.5 h-3.5 text-accent animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-opacity="0.3" stroke-width="3" />
        <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
      </svg>
      <svg v-else class="w-3.5 h-3.5 text-text-muted shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>

      <span class="text-[10px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded shrink-0"
        :class="kindBadgeClass(primary.kind)">
        {{ kindLabel(primary.kind) }}
      </span>

      <span v-if="primary.status === 'running' && primary.tokens" class="text-xs text-text-muted tabular-nums shrink-0 hidden md:inline">
        {{ primary.tokens }} tok{{ primary.tokensPerSec != null ? ` · ${primary.tokensPerSec.toFixed(1)}/s` : '' }}
      </span>
      <span v-else-if="primary.status === 'queued'" class="text-xs text-text-muted shrink-0 hidden md:inline">
        queued{{ primary.queuePosition > 0 ? ` · ${primary.queuePosition} ahead` : '' }}
      </span>

      <span class="text-xs text-text-primary truncate max-w-[180px]" :title="primary.label">
        {{ primary.label }}
      </span>

      <button
        class="shrink-0 text-[10px] uppercase tracking-wider px-2 py-0.5 border border-error/40 text-error rounded hover:bg-error/10 transition-colors cursor-pointer"
        @click="store.cancel(primary.id)"
        title="Cancel this job"
      >Stop</button>

      <span v-if="extraCount > 0" class="text-[10px] text-text-muted font-mono px-1.5 py-0.5 rounded bg-bg-primary shrink-0"
        :title="`${extraCount} more job${extraCount === 1 ? '' : 's'} active`">
        +{{ extraCount }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useJobsStore } from '../../stores/jobs.js';

const store = useJobsStore();

// Narrative + regenerate already have a dedicated streaming UI in SessionView.
const HIDDEN_KINDS = new Set(['narrative', 'regenerate']);

const visibleJobs = computed(() =>
  store.active.filter(j => !HIDDEN_KINDS.has(j.kind))
);

const primary = computed(() => visibleJobs.value[0] || {});
const extraCount = computed(() => Math.max(0, visibleJobs.value.length - 1));

const KIND_LABELS = {
  'chub-import': 'Import',
  'rerun': 'Rerun',
  'enrich': 'Enrich',
  'meta': 'Meta',
  'consolidate': 'Consolidate',
  'title': 'Title',
  'finalize-chapter': 'Finalize',
  'query': 'Ask',
};
function kindLabel(kind) { return KIND_LABELS[kind] || kind; }

const KIND_BADGE = {
  'chub-import': 'bg-accent/15 text-accent',
  'rerun': 'bg-purple-500/15 text-purple-300',
  'enrich': 'bg-purple-500/15 text-purple-300',
  'meta': 'bg-purple-500/15 text-purple-300',
  'consolidate': 'bg-purple-500/15 text-purple-300',
  'title': 'bg-emerald-500/15 text-emerald-300',
  'finalize-chapter': 'bg-emerald-500/15 text-emerald-300',
  'query': 'bg-blue-500/15 text-blue-300',
};
function kindBadgeClass(kind) {
  return KIND_BADGE[kind] || 'bg-bg-secondary text-text-secondary';
}
</script>
