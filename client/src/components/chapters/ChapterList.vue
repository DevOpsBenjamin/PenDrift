<template>
  <div class="p-3">
    <h3 class="text-[11px] font-semibold uppercase tracking-widest text-text-muted mb-3">Chapters</h3>
    <ul class="space-y-0.5">
      <li
        v-for="chapter in chapters"
        :key="chapter.id"
        class="px-3 py-2 rounded-lg cursor-pointer text-sm transition-all duration-150"
        :class="chapter.id === currentChapterId
          ? 'bg-bg-surface text-text-primary font-medium'
          : 'text-text-secondary hover:bg-bg-surface/50 hover:text-text-primary'"
        @click="$emit('select', chapter.id)"
      >
        {{ chapter.title }}
      </li>
    </ul>
    <button
      class="w-full mt-2 py-2 border border-dashed border-border rounded-lg text-text-muted text-xs
             hover:border-accent/40 hover:text-accent transition-all cursor-pointer"
      @click="$emit('create')"
    >+ New Chapter</button>
  </div>
</template>

<script setup>
defineProps({
  chapters: Array,
  currentChapterId: String,
});
defineEmits(['select', 'create']);
</script>
