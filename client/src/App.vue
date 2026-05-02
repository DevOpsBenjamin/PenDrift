<template>
  <div id="pendrift" class="h-dvh flex flex-col">
    <AppHeader />
    <RouterView />
    <JobsToastBar />
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, watch } from 'vue';
import { RouterView } from 'vue-router';
import AppHeader from './components/layout/AppHeader.vue';
import JobsToastBar from './components/layout/JobsToastBar.vue';
import { useJobsStore } from './stores/jobs.js';
import { useSettingsStore } from './stores/settings.js';

const jobs = useJobsStore();
const settings = useSettingsStore();

onMounted(() => jobs.connect());
onUnmounted(() => jobs.disconnect());

// App-wide: when a chub-import / rerun / enrich job completes anywhere,
// refresh the templates list so the sidebar stays in sync regardless of
// which view the user is currently on. View-specific behaviour (opening
// the freshly-imported template in the editor) lives in TemplatesView and
// only fires when that view is mounted.
const seenTerminal = new Set();
watch(() => jobs.jobs, (current) => {
  for (const j of current) {
    if (j.status !== 'done') continue;
    if (seenTerminal.has(j.id)) continue;
    if (j.kind === 'chub-import' || j.kind === 'rerun' || j.kind === 'enrich') {
      seenTerminal.add(j.id);
      settings.fetchTemplates();
    }
  }
}, { deep: true });
</script>
