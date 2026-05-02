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

    async updateCurrentPreset(presetId) {
      if (!this.currentSession) return;
      try {
        const updated = await sessionsApi.updateSession(this.currentSession.id, { settingsPresetId: presetId });
        this.currentSession = updated;
        // Update the matching session in the list too
        const idx = this.sessions.findIndex(s => s.id === updated.id);
        if (idx >= 0) this.sessions[idx] = updated;
      } catch (err) {
        this.error = err.message;
      }
    },

    async updateCurrentTemplateVersion(version) {
      if (!this.currentSession) return;
      try {
        const updated = await sessionsApi.setSessionTemplateVersion(this.currentSession.id, version);
        this.currentSession = updated;
        const idx = this.sessions.findIndex(s => s.id === updated.id);
        if (idx >= 0) this.sessions[idx] = updated;
      } catch (err) {
        this.error = err.message;
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
