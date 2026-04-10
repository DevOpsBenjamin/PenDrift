<template>
  <div class="character-panel">
    <h3>
      Characters
      <span v-if="updating" class="update-badge">Updating...</span>
    </h3>
    <div v-if="characters.length === 0" class="empty">No characters</div>
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

<style scoped>
.character-panel {
  padding: 1rem;
  border-top: 1px solid var(--color-border);
}

h3 {
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-secondary);
  margin-bottom: 0.75rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.update-badge {
  font-size: 0.7rem;
  text-transform: none;
  letter-spacing: normal;
  color: var(--color-accent);
  animation: blink 1s infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.empty {
  font-size: 0.85rem;
  color: var(--color-text-secondary);
  font-style: italic;
}
</style>
