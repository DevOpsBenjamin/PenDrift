<template>
  <div
    class="group relative bg-bg-secondary border border-border rounded-xl p-5 cursor-pointer
           transition-all duration-200 hover:border-accent/40 hover:shadow-lg hover:shadow-accent/5 hover:-translate-y-0.5"
    @click="$emit('select', session.id)"
  >
    <div class="flex justify-between items-start mb-3">
      <div class="flex items-start gap-2 pr-4 flex-1 min-w-0">
        <h3 class="text-base font-semibold leading-tight truncate">{{ session.title }}</h3>
        <span
          v-if="session.finishedAt"
          class="shrink-0 mt-0.5 px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wider rounded
                 bg-purple-500/15 text-purple-300 border border-purple-400/30"
          title="This session is finished (read-only). Open it and click Reopen Session to keep writing."
        >Finished</span>
      </div>
      <button
        class="opacity-0 group-hover:opacity-100 transition-opacity text-text-muted hover:text-accent p-1 -m-1"
        @click.stop="$emit('delete', session.id)"
        title="Delete session"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
    <div class="flex justify-between text-xs text-text-muted">
      <span>{{ session.chapters?.length || 0 }} chapter(s)</span>
      <span>{{ formatDate(session.updatedAt) }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({ session: Object });
defineEmits(['select', 'delete']);

function formatDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}
</script>
