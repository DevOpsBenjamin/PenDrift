import { defineStore } from 'pinia';
import * as jobsApi from '../api/jobs.js';

/**
 * Global jobs store. Mirrors `services/job_manager.py`.
 *
 * Subscribes to `/api/jobs/stream` once on first read so the toast bar +
 * Activity view stay in sync with the backend without polling. Each
 * snapshot from the backend overwrites our local list, so the store is
 * always authoritative on what's queued/running/recent.
 */
export const useJobsStore = defineStore('jobs', {
  state: () => ({
    jobs: [],          // [{id, kind, label, sessionId, status, queuePosition, ...}]
    eventSource: null,
    connected: false,
  }),

  getters: {
    active: (state) => state.jobs.filter(j => j.status === 'queued' || j.status === 'running'),
    running: (state) => state.jobs.find(j => j.status === 'running') || null,
    queued: (state) => state.jobs.filter(j => j.status === 'queued'),
    recent: (state) => state.jobs.filter(j => j.status === 'done' || j.status === 'cancelled' || j.status === 'error'),

    byId: (state) => (id) => state.jobs.find(j => j.id === id) || null,

    byKind: (state) => (kind) => state.jobs.filter(j => j.kind === kind),

    /** Latest job of a given kind that is currently active. */
    activeByKind: (state) => (kind) =>
      state.jobs.find(j => j.kind === kind && (j.status === 'queued' || j.status === 'running')) || null,
  },

  actions: {
    /** Open the cross-job SSE stream. Idempotent: calling twice does nothing. */
    connect() {
      if (this.eventSource) return;
      this.eventSource = jobsApi.subscribeToJobsState((snapshot) => {
        if (snapshot.type === 'jobs_state') {
          this.jobs = snapshot.jobs || [];
          this.connected = true;
        }
      });
    },

    disconnect() {
      if (this.eventSource) {
        this.eventSource.close();
        this.eventSource = null;
        this.connected = false;
      }
    },

    async cancel(jobId) {
      try {
        await jobsApi.cancelJob(jobId);
      } catch (err) {
        console.warn(`[jobs] cancel ${jobId} failed:`, err.message || err);
      }
    },
  },
});
