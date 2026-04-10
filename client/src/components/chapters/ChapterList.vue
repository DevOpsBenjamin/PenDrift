<template>
  <div class="chapter-list">
    <h3>Chapters</h3>
    <ul>
      <li
        v-for="chapter in chapters"
        :key="chapter.id"
        :class="{ active: chapter.id === currentChapterId }"
        @click="$emit('select', chapter.id)"
      >
        {{ chapter.title }}
      </li>
    </ul>
    <button class="btn-add" @click="$emit('create')">+ New Chapter</button>
  </div>
</template>

<script setup>
defineProps({
  chapters: Array,
  currentChapterId: String,
});
defineEmits(['select', 'create']);
</script>

<style scoped>
.chapter-list {
  padding: 1rem;
}

h3 {
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-secondary);
  margin-bottom: 0.75rem;
}

ul {
  list-style: none;
  padding: 0;
}

li {
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.9rem;
  color: var(--color-text-secondary);
  transition: background 0.15s;
}

li:hover {
  background: var(--color-bg-surface);
}

li.active {
  background: var(--color-bg-surface);
  color: var(--color-text-primary);
  font-weight: 600;
}

.btn-add {
  width: 100%;
  margin-top: 0.5rem;
  padding: 0.4rem;
  background: none;
  border: 1px dashed var(--color-border);
  border-radius: 6px;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 0.8rem;
}

.btn-add:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}
</style>
