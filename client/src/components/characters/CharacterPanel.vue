<template>
  <div class="p-3 border-t border-border-subtle">
    <h3 class="text-[11px] font-semibold uppercase tracking-widest text-text-muted mb-3 flex items-center gap-2">
      Characters
      <span
        v-if="updating"
        class="text-[10px] normal-case tracking-normal text-accent font-normal animate-pulse"
      >Updating...</span>
    </h3>
    <div v-if="characters.length === 0" class="text-xs text-text-muted italic">
      No characters yet
    </div>
    <CharacterCard
      v-for="char in characters"
      :key="char.name"
      :character="char"
    />
  </div>
</template>

<script setup>
import CharacterCard from './CharacterCard.vue';

defineProps({
  characters: Array,
  updating: Boolean,
});
</script>
