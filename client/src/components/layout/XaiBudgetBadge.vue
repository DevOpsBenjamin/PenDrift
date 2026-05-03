<template>
  <div v-if="budget?.configured" class="relative" v-click-outside="() => (open = false)">
    <button
      type="button"
      class="flex items-center gap-2 px-3 py-1.5 bg-bg-surface/70 hover:bg-bg-surface border border-border-subtle hover:border-accent/40 rounded-lg text-xs transition-all cursor-pointer"
      :title="tooltip"
      @click="open = !open"
    >
      <span class="w-1.5 h-1.5 rounded-full" :class="dotClass"></span>
      <span class="font-mono tabular-nums" :class="budget.prepaidRemainingUsd != null ? 'text-text-primary font-medium' : 'text-text-muted'">
        {{ remainingLabel }}
      </span>
      <span v-if="budget.estimated" class="text-[10px] text-amber-400 font-mono">≈</span>
      <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 text-text-muted transition-transform" :class="open ? 'rotate-180' : ''" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
      </svg>
    </button>

    <Transition name="drop">
      <div
        v-if="open"
        class="absolute top-full mt-2 left-1/2 -translate-x-1/2 w-72 bg-bg-secondary border border-border rounded-xl shadow-xl p-4 z-50"
      >
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-xs font-semibold uppercase tracking-wider text-text-secondary">xAI Budget</h3>
          <button
            class="text-xs text-accent hover:underline cursor-pointer disabled:opacity-50"
            :disabled="refreshing"
            @click="doRefresh"
          >{{ refreshing ? 'Syncing…' : 'Refresh' }}</button>
        </div>

        <div v-if="budget.lastError" class="mb-3 px-2 py-1.5 bg-error/10 border border-error/30 rounded text-xs text-error">
          {{ budget.lastError }}
        </div>

        <div class="space-y-2">
          <div class="flex justify-between items-baseline">
            <span class="text-xs text-text-muted">Remaining</span>
            <span class="font-mono tabular-nums text-base text-text-primary">
              {{ usdLabel(budget.prepaidRemainingUsd) }}
            </span>
          </div>
          <div class="flex justify-between items-baseline">
            <span class="text-xs text-text-muted">Used this cycle</span>
            <span class="font-mono tabular-nums text-xs text-text-secondary">
              {{ usdLabel(budget.prepaidUsedUsd) }}
            </span>
          </div>
          <div class="flex justify-between items-baseline">
            <span class="text-xs text-text-muted">Total prepaid</span>
            <span class="font-mono tabular-nums text-xs text-text-muted">
              {{ usdLabel(budget.prepaidTotalUsd) }}
            </span>
          </div>
        </div>

        <div class="mt-3 pt-3 border-t border-border-subtle space-y-1.5">
          <div class="flex items-center gap-2 text-xs">
            <span class="w-1.5 h-1.5 rounded-full" :class="dotClass"></span>
            <span :class="budget.estimated ? 'text-amber-400' : 'text-green-400'">
              {{ budget.estimated ? 'Estimated' : 'Synced' }}
            </span>
            <span v-if="budget.lastSyncedAt" class="text-text-muted">
              · {{ syncedAgo }}
            </span>
          </div>
          <div v-if="budget.estimated" class="text-[11px] text-text-muted leading-snug">
            {{ budget.localDecrementsSinceSync }} call{{ budget.localDecrementsSinceSync === 1 ? '' : 's' }} since last sync.
            Local estimate may miss usage from outside PenDrift.
          </div>
          <div v-if="cycleLabel" class="text-[11px] text-text-muted">
            Billing cycle: {{ cycleLabel }}
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import * as llmApi from '../../api/llm.js';
import { useJobsStore } from '../../stores/jobs.js';

const jobs = useJobsStore();

const budget = ref(null);
const open = ref(false);
const refreshing = ref(false);
const now = ref(Date.now());

let pollTimer = null;
let clockTimer = null;
let visibilityHandler = null;

// Background polling cadence — only fires to catch usage that happened outside
// PenDrift (e.g. another client of the same xAI team). In-app calls update the
// in-RAM state on the backend immediately and are surfaced via the jobs-done
// hook below, so we don't need rapid polling.
const POLL_MS = 30_000;

async function fetchBudget() {
  if (typeof document !== 'undefined' && document.hidden) return;
  try {
    budget.value = await llmApi.getXaiBudget();
  } catch {
    /* ignore — keep previous state */
  }
}

async function doRefresh() {
  refreshing.value = true;
  try {
    budget.value = await llmApi.refreshXaiBudget();
  } catch (e) {
    /* error surfaces via budget.lastError on next get */
  } finally {
    refreshing.value = false;
  }
}

// Refetch immediately when the set of active jobs shrinks — that's when an
// LLM call just finished and the in-RAM budget on the backend was decremented.
watch(
  () => jobs.active.length,
  (curr, prev) => {
    if (prev != null && curr < prev) fetchBudget();
  },
);

onMounted(() => {
  fetchBudget();
  pollTimer = setInterval(fetchBudget, POLL_MS);
  clockTimer = setInterval(() => (now.value = Date.now()), 1000);
  // Refetch once when the tab becomes visible after being hidden — the timer
  // was paused via the document.hidden guard, so we may have stale data.
  visibilityHandler = () => { if (!document.hidden) fetchBudget(); };
  document.addEventListener('visibilitychange', visibilityHandler);
});

onUnmounted(() => {
  clearInterval(pollTimer);
  clearInterval(clockTimer);
  if (visibilityHandler) document.removeEventListener('visibilitychange', visibilityHandler);
});

const remainingLabel = computed(() => {
  if (!budget.value || budget.value.prepaidRemainingUsd == null) return '—';
  return '$' + budget.value.prepaidRemainingUsd.toFixed(4);
});

const dotClass = computed(() => {
  if (!budget.value) return 'bg-text-muted/40';
  if (budget.value.lastError) return 'bg-error';
  return budget.value.estimated ? 'bg-amber-400' : 'bg-green-400';
});

const tooltip = computed(() => {
  if (!budget.value) return '';
  if (budget.value.lastError) return `Error: ${budget.value.lastError}`;
  return budget.value.estimated
    ? 'Estimated locally — click to refresh'
    : 'Synced with xAI';
});

const cycleLabel = computed(() => {
  const c = budget.value?.billingCycle;
  if (!c?.year || !c?.month) return '';
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${monthNames[c.month - 1]} ${c.year}`;
});

const syncedAgo = computed(() => {
  const ts = budget.value?.lastSyncedAt;
  if (!ts) return '';
  const secs = Math.max(0, now.value / 1000 - ts);
  if (secs < 60) return `${Math.floor(secs)}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  return `${Math.floor(secs / 3600)}h ago`;
});

function usdLabel(v) {
  if (v == null) return '—';
  return '$' + v.toFixed(4);
}

const vClickOutside = {
  mounted(el, binding) {
    el._clickOutside = (e) => {
      if (!el.contains(e.target)) binding.value();
    };
    document.addEventListener('click', el._clickOutside);
  },
  unmounted(el) {
    document.removeEventListener('click', el._clickOutside);
  },
};
</script>

<style scoped>
.drop-enter-active,
.drop-leave-active {
  transition: transform 0.15s ease, opacity 0.15s ease;
}
.drop-enter-from,
.drop-leave-to {
  transform: translateY(-4px);
  opacity: 0;
}
</style>
