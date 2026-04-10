import { defineStore } from 'pinia';

export const useUiStore = defineStore('ui', {
  state: () => ({
    sidebarOpen: true,
    toasts: [],
  }),

  actions: {
    toggleSidebar() {
      this.sidebarOpen = !this.sidebarOpen;
    },

    addToast(message, type = 'error', duration = 5000) {
      const id = Date.now();
      this.toasts.push({ id, message, type });
      setTimeout(() => {
        this.toasts = this.toasts.filter(t => t.id !== id);
      }, duration);
    },
  },
});
