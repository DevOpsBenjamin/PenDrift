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

/**
 * Subscribe to a single job's event stream — replays the buffered events
 * first, then forwards live ones until the job terminates.
 */
export function subscribeToJob(jobId, onEvent, onClose) {
  const es = new EventSource(`/api/jobs/${jobId}/stream`);
  es.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data));
    } catch (e) {
      console.warn(`[jobs/${jobId}] bad event:`, msg.data, e);
    }
  };
  es.onerror = () => {
    // Server closes the stream when the job is terminal — that surfaces as
    // an error here. Notify the caller, then close to stop auto-reconnect.
    if (onClose) onClose();
    es.close();
  };
  return es;
}
