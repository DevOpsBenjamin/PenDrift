<template>
  <div class="p-3 border-t border-border-subtle">
    <h3 class="text-[11px] font-semibold uppercase tracking-widest text-text-muted mb-3 flex items-center gap-2">
      Characters
      <span
        v-if="updating"
        class="text-[10px] normal-case tracking-normal text-accent font-normal animate-pulse"
      >Analyzing...</span>
    </h3>
    <div v-if="characters.length === 0" class="text-xs text-text-muted italic">
      No characters yet
    </div>
    <ul class="space-y-1">
      <li
        v-for="char in characters"
        :key="char.name"
        class="flex items-center justify-between px-2 py-1.5 rounded-md text-sm text-text-secondary
               hover:bg-bg-surface/50 transition-all"
      >
        <span class="truncate">{{ char.name }}</span>
        <button
          class="text-text-muted hover:text-accent transition-colors shrink-0 p-0.5"
          @click="inspecting = char"
          title="View character sheet"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            <path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
          </svg>
        </button>
      </li>
    </ul>

    <!-- Consistency warnings -->
    <div v-if="flags.length" class="mt-3 space-y-1">
      <h4 class="text-[10px] font-semibold uppercase tracking-wider text-warning mb-1">Flags</h4>
      <p
        v-for="(flag, i) in flags"
        :key="i"
        class="text-[10px] text-warning/80 leading-relaxed bg-warning/5 rounded px-2 py-1"
      >{{ flag }}</p>
    </div>

    <!-- Character inspect popup -->
    <Teleport to="body">
      <div
        v-if="inspecting"
        class="fixed inset-0 bg-bg-overlay backdrop-blur-sm flex items-center justify-center z-50 p-4"
        @click.self="inspecting = null"
      >
        <div class="bg-bg-secondary border border-border rounded-2xl p-6 w-full max-w-md shadow-2xl">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-lg font-semibold text-accent">{{ inspecting.name }}</h2>
            <button
              class="text-text-muted hover:text-text-primary transition-colors p-1"
              @click="inspecting = null"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div class="space-y-3">
            <div v-if="inspecting.currentState">
              <h4 class="text-[11px] font-semibold uppercase tracking-wider text-text-muted mb-1">Current State</h4>
              <p class="text-sm text-text-secondary leading-relaxed">{{ inspecting.currentState }}</p>
            </div>

            <div v-if="inspecting.traits?.length">
              <h4 class="text-[11px] font-semibold uppercase tracking-wider text-text-muted mb-1">Traits</h4>
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="trait in inspecting.traits"
                  :key="trait"
                  class="text-xs px-2 py-0.5 bg-bg-surface rounded-full text-text-secondary"
                >{{ trait }}</span>
              </div>
            </div>

            <div v-if="inspecting.keyEvents?.length">
              <h4 class="text-[11px] font-semibold uppercase tracking-wider text-text-muted mb-1">Key Events</h4>
              <ul class="space-y-1">
                <li
                  v-for="event in inspecting.keyEvents"
                  :key="event"
                  class="text-xs text-text-secondary leading-relaxed"
                >- {{ event }}</li>
              </ul>
            </div>

            <div v-if="inspecting.lastUpdated" class="text-[10px] text-text-muted pt-2 border-t border-border-subtle">
              Last updated: {{ new Date(inspecting.lastUpdated).toLocaleString() }}
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref } from 'vue';

defineProps({
  characters: Array,
  updating: Boolean,
  flags: { type: Array, default: () => [] },
});

const inspecting = ref(null);
</script>
