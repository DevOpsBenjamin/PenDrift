<template>
  <div class="narrative-display" ref="container">
    <div v-if="chunks.length === 0" class="empty-narrative">
      <p>The story hasn't begun yet.</p>
      <p>Write a directive below to start.</p>
    </div>

    <ChunkBlock
      v-for="(chunk, i) in chunks"
      :key="chunk.id"
      :chunk="chunk"
      :isLast="i === chunks.length - 1"
      @regenerate="$emit('regenerate')"
      @delete="$emit('delete')"
    />

    <div v-if="generating" class="generating-indicator">
      <span class="dot"></span>
      <span class="dot"></span>
      <span class="dot"></span>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue';
import ChunkBlock from './ChunkBlock.vue';

const props = defineProps({
  chunks: Array,
  generating: Boolean,
});

defineEmits(['regenerate', 'delete']);

const container = ref(null);

watch(() => props.chunks.length, async () => {
  await nextTick();
  if (container.value) {
    container.value.scrollTop = container.value.scrollHeight;
  }
});
</script>

<style scoped>
.narrative-display {
  flex: 1;
  overflow-y: auto;
  padding: 2rem 3rem;
  max-width: 800px;
  margin: 0 auto;
}

.empty-narrative {
  text-align: center;
  color: var(--color-text-secondary);
  padding: 4rem 0;
  line-height: 2;
  font-style: italic;
}

.generating-indicator {
  display: flex;
  gap: 0.4rem;
  padding: 1rem 0;
  justify-content: center;
}

.dot {
  width: 8px;
  height: 8px;
  background: var(--color-accent);
  border-radius: 50%;
  animation: pulse 1.4s infinite ease-in-out;
}

.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes pulse {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}
</style>
