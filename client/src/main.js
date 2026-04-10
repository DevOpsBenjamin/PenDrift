import { createApp } from 'vue';
import { createPinia } from 'pinia';
import { createRouter, createWebHistory } from 'vue-router';
import App from './App.vue';
import './style.css';

const routes = [
  { path: '/', name: 'home', component: () => import('./views/HomeView.vue') },
  { path: '/session/:id', name: 'session', component: () => import('./views/SessionView.vue') },
  { path: '/settings', name: 'settings', component: () => import('./views/SettingsView.vue') },
  { path: '/templates', name: 'templates', component: () => import('./views/TemplatesView.vue') },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.mount('#app');
