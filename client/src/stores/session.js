import { defineStore } from 'pinia';
import * as sessionsApi from '../api/sessions.js';
import * as templatesApi from '../api/templates.js';

export const useSessionStore = defineStore('session', {
  state: () => ({
    sessions: [],
    currentSession: null,
    templates: [],
    loading: false,
    error: null,
  }),

  actions: {
    async fetchSessions() {
      this.loading = true;
      this.error = null;
      try {
        this.sessions = await sessionsApi.listSessions();
      } catch (err) {
        this.error = err.message;
      } finally {
        this.loading = false;
      }
    },

    async fetchTemplates() {
      try {
        this.templates = await templatesApi.listTemplates();
      } catch (err) {
        this.error = err.message;
      }
    },

    async loadSession(id) {
      this.loading = true;
      this.error = null;
      try {
        this.currentSession = await sessionsApi.getSession(id);
      } catch (err) {
        this.error = err.message;
      } finally {
        this.loading = false;
      }
    },

    async createSession({ templateId, title, settingsPresetId }) {
      this.error = null;
      try {
        const session = await sessionsApi.createSession({ templateId, title, settingsPresetId });
        this.sessions.unshift(session);
        return session;
      } catch (err) {
        this.error = err.message;
        return null;
      }
    },

    async deleteSession(id) {
      this.error = null;
      try {
        await sessionsApi.deleteSession(id);
        this.sessions = this.sessions.filter(s => s.id !== id);
        if (this.currentSession?.id === id) {
          this.currentSession = null;
        }
      } catch (err) {
        this.error = err.message;
      }
    },
  },
});
