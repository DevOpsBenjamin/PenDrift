<template>
  <div class="flex-1 overflow-y-auto px-4 sm:px-8 lg:px-12 py-6 sm:py-10" ref="container">
    <div class="max-w-2xl mx-auto">
      <div v-if="chunks.length === 0" class="text-center py-20 sm:py-32">
        <p class="text-text-secondary text-lg italic">The story hasn't begun yet.</p>
        <p class="text-text-muted text-sm mt-2">Write a directive below to start.</p>
      </div>

      <ChunkBlock
        v-for="(chunk, i) in chunks"
        :key="chunk.id"
        :chunk="chunk"
        :isLast="i === chunks.length - 1"
        @regenerate="(chunkId) => $emit('regenerate', chunkId)"
        @delete="$emit('delete')"
        @edit="$emit('edit', $event)"
        @switchVersion="$emit('switchVersion', $event)"
      />

      <div v-if="generating" class="flex gap-1.5 py-6 justify-center">
        <span class="w-2 h-2 bg-accent rounded-full animate-bounce" style="animation-delay: 0ms"></span>
        <span class="w-2 h-2 bg-accent rounded-full animate-bounce" style="animation-delay: 150ms"></span>
        <span class="w-2 h-2 bg-accent rounded-full animate-bounce" style="animation-delay: 300ms"></span>
      </div>
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

defineEmits(['regenerate', 'delete', 'edit', 'switchVersion']);

const container = ref(null);

watch(() => props.chunks.length, async () => {
  await nextTick();
  if (container.value) {
    container.value.scrollTop = container.value.scrollHeight;
  }
});
</script>
