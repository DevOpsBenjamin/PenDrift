import { defineStore } from 'pinia';
import * as presetsApi from '../api/presets.js';
import * as templatesApi from '../api/templates.js';

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    presets: [],
    templates: [],
    loading: false,
    error: null,
  }),

  actions: {
    async fetchPresets() {
      this.loading = true;
      try {
        this.presets = await presetsApi.listSettingsPresets();
      } catch (err) {
        this.error = err.message;
      } finally {
        this.loading = false;
      }
    },

    async savePreset(preset) {
      try {
        const saved = await presetsApi.saveSettingsPreset(preset);
        const idx = this.presets.findIndex(p => p.id === saved.id);
        if (idx >= 0) {
          this.presets[idx] = saved;
        } else {
          this.presets.push(saved);
        }
        return saved;
      } catch (err) {
        this.error = err.message;
        return null;
      }
    },

    async deletePreset(id) {
      try {
        await presetsApi.deleteSettingsPreset(id);
        this.presets = this.presets.filter(p => p.id !== id);
      } catch (err) {
        this.error = err.message;
      }
    },

    async fetchTemplates() {
      this.loading = true;
      try {
        this.templates = await templatesApi.listTemplates();
      } catch (err) {
        this.error = err.message;
      } finally {
        this.loading = false;
      }
    },

    async saveTemplate(template) {
      try {
        const saved = await templatesApi.saveTemplate(template);
        const idx = this.templates.findIndex(t => t.id === saved.id);
        if (idx >= 0) {
          this.templates[idx] = saved;
        } else {
          this.templates.push(saved);
        }
        return saved;
      } catch (err) {
        this.error = err.message;
        return null;
      }
    },

    async deleteTemplate(id) {
      try {
        await templatesApi.deleteTemplate(id);
        this.templates = this.templates.filter(t => t.id !== id);
      } catch (err) {
        this.error = err.message;
      }
    },
  },
});
