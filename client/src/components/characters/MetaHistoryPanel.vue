<template>
  <Teleport to="body">
    <div class="fixed inset-0 bg-bg-overlay backdrop-blur-sm flex items-center justify-center z-50 p-4" @click.self="$emit('close')">
      <div class="bg-bg-secondary border border-border rounded-2xl w-full max-w-2xl max-h-[80vh] flex flex-col shadow-2xl">
        <div class="flex items-center justify-between p-5 border-b border-border-subtle">
          <h2 class="text-lg font-semibold">Meta-Analysis History</h2>
          <button
            class="text-text-muted hover:text-text-primary transition-colors p-1"
            @click="$emit('close')"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="flex-1 overflow-y-auto p-5 space-y-4">
          <div v-if="history.length === 0" class="text-center text-text-muted italic py-10">
            No meta-analysis has run yet.
          </div>

          <div
            v-for="(entry, i) in reversedHistory"
            :key="i"
            class="border border-border-subtle rounded-xl p-4 space-y-3"
            :class="entry.status === 'failed' ? 'border-error/30' : 'border-border-subtle'"
          >
            <div class="flex items-center justify-between">
              <span class="text-xs text-text-muted">{{ formatDate(entry.timestamp) }}</span>
              <span
                class="text-[10px] px-2 py-0.5 rounded-full font-medium"
                :class="entry.status === 'success'
                  ? 'bg-success/10 text-success'
                  : 'bg-error/10 text-error'"
              >{{ entry.status }}</span>
            </div>

            <div v-if="entry.status === 'failed'" class="text-xs text-error/80">
              {{ entry.error }}
            </div>

            <template v-if="entry.result">
              <!-- Character Updates -->
              <div v-if="entry.result.characterUpdates?.length">
                <h4 class="text-[11px] font-semibold uppercase tracking-wider text-text-muted mb-1">Character Updates</h4>
                <div v-for="char in entry.result.characterUpdates" :key="char.name" class="text-xs text-text-secondary mb-1">
                  <span class="text-accent font-medium">{{ char.name }}</span> — {{ char.currentState }}
                </div>
              </div>

              <!-- New Characters -->
              <div v-if="entry.result.newCharacters?.length">
                <h4 class="text-[11px] font-semibold uppercase tracking-wider text-success mb-1">New Characters</h4>
                <div v-for="char in entry.result.newCharacters" :key="char.name" class="text-xs text-text-secondary mb-1">
                  <span class="text-success font-medium">{{ char.name }}</span> — {{ char.currentState }}
                </div>
              </div>

              <!-- Important Facts -->
              <div v-if="entry.result.importantFacts?.length">
                <h4 class="text-[11px] font-semibold uppercase tracking-wider text-text-muted mb-1">Facts Extracted</h4>
                <ul class="text-xs text-text-secondary space-y-0.5">
                  <li v-for="(fact, j) in entry.result.importantFacts" :key="j">- {{ fact }}</li>
                </ul>
              </div>

              <!-- Consistency Flags -->
              <div v-if="entry.result.consistencyFlags?.length">
                <h4 class="text-[11px] font-semibold uppercase tracking-wider text-warning mb-1">Consistency Flags</h4>
                <ul class="text-xs text-warning/80 space-y-0.5">
                  <li v-for="(flag, j) in entry.result.consistencyFlags" :key="j">- {{ flag }}</li>
                </ul>
              </div>
            </template>

            <!-- Toggle raw response -->
            <button
              v-if="entry.rawResponse"
              class="text-[10px] text-text-muted hover:text-text-secondary transition-colors cursor-pointer"
              @click="toggleRaw(i)"
            >{{ expandedRaw === i ? 'Hide' : 'Show' }} raw response</button>
            <pre
              v-if="expandedRaw === i"
              class="text-[10px] text-text-muted bg-bg-primary rounded-lg p-3 overflow-x-auto whitespace-pre-wrap max-h-48 overflow-y-auto"
            >{{ entry.rawResponse }}</pre>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, ref } from 'vue';

const props = defineProps({ history: Array });
defineEmits(['close']);

const expandedRaw = ref(null);
const reversedHistory = computed(() => [...(props.history || [])].reverse());

function toggleRaw(i) {
  expandedRaw.value = expandedRaw.value === i ? null : i;
}

function formatDate(iso) {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}
</script>
