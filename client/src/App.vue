<template>
  <div id="pendrift" class="h-dvh flex flex-col">
    <AppHeader />
    <RouterView />
  </div>
</template>

<script setup>
import { RouterView } from 'vue-router';
import AppHeader from './components/layout/AppHeader.vue';
</script>
