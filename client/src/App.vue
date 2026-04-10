<template>
  <div id="pendrift">
    <AppHeader />
    <RouterView />
  </div>
</template>

<script setup>
import { RouterView } from 'vue-router';
import AppHeader from './components/layout/AppHeader.vue';
</script>

<style>
#pendrift {
  min-height: 100vh;
}
</style>
