<template>
  <header class="flex items-center px-4 py-3 bg-bg-secondary border-b border-border-subtle backdrop-blur-sm sticky top-0 z-40">
    <div class="flex-1 flex items-center">
      <RouterLink to="/" class="font-body text-xl font-bold text-accent no-underline tracking-tight">
        PenDrift
      </RouterLink>
    </div>
    <div class="flex-1 flex justify-center items-center gap-3 min-w-0">
      <JobsHeaderInline />
      <span v-if="showSeparator" class="text-text-muted/40 select-none">|</span>
      <XaiBudgetBadge />
    </div>
    <div class="flex-1 flex justify-end items-center">
      <nav class="hidden sm:flex gap-5">
        <RouterLink
          v-for="link in links"
          :key="link.to"
          :to="link.to"
          class="text-text-secondary text-sm no-underline transition-colors duration-200 hover:text-text-primary"
          active-class="!text-text-primary font-medium"
        >
          {{ link.label }}
        </RouterLink>
      </nav>
      <!-- Mobile nav toggle -->
      <button
        class="sm:hidden p-2 text-text-secondary hover:text-text-primary transition-colors"
        @click="mobileNav = !mobileNav"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
    </div>
    <!-- Mobile nav dropdown -->
    <Transition name="slide">
      <nav
        v-if="mobileNav"
        class="absolute top-full left-0 right-0 bg-bg-secondary border-b border-border-subtle flex flex-col p-4 gap-3 sm:hidden z-50"
      >
        <RouterLink
          v-for="link in links"
          :key="link.to"
          :to="link.to"
          class="text-text-secondary text-sm no-underline py-2 px-3 rounded-lg hover:bg-bg-surface hover:text-text-primary transition-all"
          active-class="!text-text-primary !bg-bg-surface font-medium"
          @click="mobileNav = false"
        >
          {{ link.label }}
        </RouterLink>
      </nav>
    </Transition>
  </header>
</template>

<script setup>
import { ref, computed } from 'vue';
import { RouterLink } from 'vue-router';
import XaiBudgetBadge from './XaiBudgetBadge.vue';
import JobsHeaderInline from './JobsHeaderInline.vue';
import { useJobsStore } from '../../stores/jobs.js';

const mobileNav = ref(false);
const jobsStore = useJobsStore();
// Hide the visual `|` separator when one of the two sides has nothing to show,
// otherwise we'd float a lone bar in the middle of the header.
const HIDDEN_KINDS = new Set(['narrative', 'regenerate']);
const showSeparator = computed(() =>
  jobsStore.active.some(j => !HIDDEN_KINDS.has(j.kind))
);
const links = [
  { to: '/', label: 'Sessions' },
  { to: '/templates', label: 'Templates' },
  { to: '/activity', label: 'Activity' },
  { to: '/settings', label: 'Settings' },
];
</script>

<style scoped>
.slide-enter-active,
.slide-leave-active {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.slide-enter-from,
.slide-leave-to {
  transform: translateY(-8px);
  opacity: 0;
}
</style>
