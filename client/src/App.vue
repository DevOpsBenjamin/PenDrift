<template>
  <div id="pendrift" class="h-dvh flex flex-col">
    <AppHeader />
    <RouterView />
    <JobsToastBar />
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue';
import { RouterView } from 'vue-router';
import AppHeader from './components/layout/AppHeader.vue';
import JobsToastBar from './components/layout/JobsToastBar.vue';
import { useJobsStore } from './stores/jobs.js';

const jobs = useJobsStore();
onMounted(() => jobs.connect());
onUnmounted(() => jobs.disconnect());
</script>
