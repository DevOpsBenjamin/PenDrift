import api from './client.js';

/** Snapshot of all known jobs (active first, then recent history). */
export const listJobs = () => api.get('jobs').json();

/** Detail of a single job, including its full event log. */
export const getJob = (jobId) => api.get(`jobs/${jobId}`).json();

/** Cancel a queued or running job. No-op if already terminal. */
export const cancelJob = (jobId) => api.post(`jobs/${jobId}/cancel`).json();

/**
 * Subscribe to cross-job state updates as Server-Sent Events. Each message is
 * a `{type: 'jobs_state', jobs: [...]}` snapshot. Returns the EventSource so
 * the caller can `close()` it.
 *
 * This is the ONLY job stream the frontend opens. Per-job streams were
 * removed when we consolidated to a single SSE connection — opening one
 * EventSource per running job ate browser HTTP/1.1 connection-pool slots
 * and starved JS chunk + activity polling fetches under load.
 */
export function subscribeToJobsState(onSnapshot) {
  const es = new EventSource('/api/jobs/stream');
  es.onmessage = (msg) => {
    try {
      onSnapshot(JSON.parse(msg.data));
    } catch (e) {
      console.warn('[jobs] bad snapshot:', msg.data, e);
    }
  };
  es.onerror = (e) => {
    // EventSource auto-reconnects; we just log so a flaky connection is visible.
    console.debug('[jobs] state stream error (will retry)', e);
  };
  return es;
}
