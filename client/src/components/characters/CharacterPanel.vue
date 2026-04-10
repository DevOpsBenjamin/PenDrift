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
    <CharacterCard
      v-for="char in characters"
      :key="char.name"
      :character="char"
    />

    <!-- Consistency warnings -->
    <div v-if="flags.length" class="mt-3 space-y-1">
      <h4 class="text-[10px] font-semibold uppercase tracking-wider text-warning mb-1">Consistency Flags</h4>
      <p
        v-for="(flag, i) in flags"
        :key="i"
        class="text-[10px] text-warning/80 leading-relaxed bg-warning/5 rounded px-2 py-1"
      >{{ flag }}</p>
    </div>
  </div>
</template>

<script setup>
import CharacterCard from './CharacterCard.vue';

defineProps({
  characters: Array,
  updating: Boolean,
  flags: { type: Array, default: () => [] },
});
</script>
