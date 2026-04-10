<template>
  <div class="p-3 bg-bg-primary/60 rounded-lg mb-2 border border-border-subtle">
    <h4 class="text-sm font-semibold text-accent mb-1">{{ character.name }}</h4>
    <p v-if="character.currentState" class="text-xs text-text-secondary italic mb-2 leading-relaxed">
      {{ character.currentState }}
    </p>
    <div v-if="character.traits?.length" class="flex flex-wrap gap-1 mb-2">
      <span
        v-for="trait in character.traits"
        :key="trait"
        class="text-[10px] px-2 py-0.5 bg-bg-surface rounded-full text-text-muted"
      >{{ trait }}</span>
    </div>
    <div v-if="character.keyEvents?.length" class="space-y-0.5">
      <p
        v-for="event in character.keyEvents"
        :key="event"
        class="text-[10px] text-text-muted leading-relaxed"
      >{{ event }}</p>
    </div>
  </div>
</template>

<script setup>
defineProps({ character: Object });
</script>
