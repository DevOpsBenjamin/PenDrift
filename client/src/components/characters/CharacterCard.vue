<template>
  <div class="character-card">
    <h4>{{ character.name }}</h4>
    <p class="state">{{ character.currentState }}</p>
    <div v-if="character.traits?.length" class="traits">
      <span v-for="trait in character.traits" :key="trait" class="trait">{{ trait }}</span>
    </div>
    <div v-if="character.keyEvents?.length" class="events">
      <p v-for="event in character.keyEvents" :key="event" class="event">{{ event }}</p>
    </div>
  </div>
</template>

<script setup>
defineProps({ character: Object });
</script>

<style scoped>
.character-card {
  padding: 0.75rem;
  background: var(--color-bg-primary);
  border-radius: 6px;
  margin-bottom: 0.5rem;
}

h4 {
  font-size: 0.95rem;
  margin-bottom: 0.35rem;
  color: var(--color-accent);
}

.state {
  font-size: 0.85rem;
  color: var(--color-text-secondary);
  font-style: italic;
  margin-bottom: 0.35rem;
}

.traits {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin-bottom: 0.35rem;
}

.trait {
  font-size: 0.75rem;
  padding: 0.15rem 0.5rem;
  background: var(--color-bg-surface);
  border-radius: 10px;
  color: var(--color-text-secondary);
}

.events {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.event {
  margin-bottom: 0.15rem;
}
</style>
