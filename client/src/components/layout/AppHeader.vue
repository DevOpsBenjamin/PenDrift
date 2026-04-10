<template>
  <header class="app-header">
    <RouterLink to="/" class="logo">PenDrift</RouterLink>
    <nav>
      <RouterLink to="/">Sessions</RouterLink>
      <RouterLink to="/templates">Templates</RouterLink>
      <RouterLink to="/settings">Settings</RouterLink>
    </nav>
  </header>
</template>

<script setup>
import { RouterLink } from 'vue-router';
</script>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1.5rem;
  background: var(--color-bg-secondary);
  border-bottom: 1px solid var(--color-border);
}

.logo {
  font-family: var(--font-body);
  font-size: 1.4rem;
  font-weight: bold;
  color: var(--color-accent);
  text-decoration: none;
}

nav {
  display: flex;
  gap: 1.5rem;
}

nav a {
  color: var(--color-text-secondary);
  text-decoration: none;
  font-size: 0.9rem;
  transition: color 0.2s;
}

nav a:hover,
nav a.router-link-active {
  color: var(--color-text-primary);
}
</style>
