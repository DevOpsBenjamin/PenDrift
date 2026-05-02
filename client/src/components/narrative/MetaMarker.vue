<template>
  <div class="my-3">
    <button
      type="button"
      class="w-full flex items-center gap-3 py-2 px-3 rounded-lg cursor-pointer transition-colors group"
      :class="open
        ? 'bg-purple-500/10 border border-purple-500/30'
        : 'bg-bg-surface/30 hover:bg-purple-500/5 border border-transparent'"
      @click="open = !open"
    >
      <div class="flex-1 flex items-center gap-3 text-xs text-text-muted">
        <span class="h-px flex-1 bg-purple-500/20"></span>
        <span class="flex items-center gap-2 shrink-0">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          <span class="text-purple-300 font-medium">{{ summaryText }}</span>
          <span v-if="entry.status === 'failed'" class="text-error">· failed</span>
        </span>
        <span class="h-px flex-1 bg-purple-500/20"></span>
        <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 transition-transform shrink-0" :class="open ? 'rotate-180' : ''" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </div>
    </button>

    <div v-if="open" class="mt-2 ml-4 mr-4 p-3 bg-bg-surface/40 rounded-lg border border-purple-500/20 text-xs space-y-2">
      <div v-if="entry.error" class="text-error">{{ entry.error }}</div>

      <div v-if="charUpdates.length">
        <div class="text-purple-300 font-semibold mb-1">Character updates ({{ charUpdates.length }})</div>
        <ul class="space-y-1 text-text-secondary">
          <li v-for="c in charUpdates" :key="c.name" class="leading-snug">
            <span class="font-mono text-text-primary">{{ c.name }}</span>
            <span v-if="c.currentState"> — {{ c.currentState }}</span>
          </li>
        </ul>
      </div>

      <div v-if="newChars.length">
        <div class="text-purple-300 font-semibold mb-1">New characters ({{ newChars.length }})</div>
        <ul class="space-y-1 text-text-secondary">
          <li v-for="c in newChars" :key="c.name">
            <span class="font-mono text-text-primary">{{ c.name }}</span>
            <span v-if="c.currentState"> — {{ c.currentState }}</span>
          </li>
        </ul>
      </div>

      <div v-if="facts.length">
        <div class="text-purple-300 font-semibold mb-1">Facts after this run ({{ facts.length }})</div>
        <ul class="space-y-0.5 text-text-secondary list-disc list-inside">
          <li v-for="(f, i) in facts" :key="i" class="leading-snug">{{ f }}</li>
        </ul>
      </div>

      <div v-if="flags.length">
        <div class="text-error font-semibold mb-1">Consistency flags ({{ flags.length }})</div>
        <ul class="space-y-0.5 text-text-secondary list-disc list-inside">
          <li v-for="(f, i) in flags" :key="i" class="leading-snug">{{ f }}</li>
        </ul>
      </div>

      <div class="text-text-muted text-[10px] pt-1 flex justify-between">
        <span>{{ formattedTime }}</span>
        <span v-if="entry.chunkRange?.count">{{ entry.chunkRange.count }} chunks analyzed</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue';

const props = defineProps({
  entry: { type: Object, required: true },
});

const open = ref(false);

const result = computed(() => props.entry.result || {});
const charUpdates = computed(() => result.value.characterUpdates || []);
const newChars = computed(() => result.value.newCharacters || []);
const facts = computed(() => result.value.importantFacts || []);
const flags = computed(() => result.value.consistencyFlags || []);

const summaryText = computed(() => {
  const parts = [];
  if (charUpdates.value.length) parts.push(`${charUpdates.value.length} char update${charUpdates.value.length !== 1 ? 's' : ''}`);
  if (newChars.value.length) parts.push(`${newChars.value.length} new`);
  if (facts.value.length) parts.push(`${facts.value.length} facts`);
  if (flags.value.length) parts.push(`${flags.value.length} flag${flags.value.length !== 1 ? 's' : ''}`);
  if (!parts.length) parts.push('no changes');
  return `Meta-analysis · ${parts.join(' · ')}`;
});

const formattedTime = computed(() => {
  if (!props.entry.timestamp) return '';
  try {
    return new Date(props.entry.timestamp).toLocaleString();
  } catch {
    return props.entry.timestamp;
  }
});
</script>
