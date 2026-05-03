/**
 * Browser-side network instrumentation. Wraps `fetch` and `EventSource`
 * globally so we can see — in the console — when:
 *  - a fetch is pending too long (likely waiting for an HTTP/1.1 pool slot)
 *  - the total number of concurrent connections approaches the browser's
 *    per-origin limit (~6 for HTTP/1.1)
 *
 * Usage:
 *   - Loaded automatically from `main.js`.
 *   - Call `window.__netDebug()` in the DevTools console to dump the current
 *     state (open SSEs + in-flight fetches with their elapsed time).
 *   - Watch the console for `[netDebug]` warnings when something hangs.
 *
 * The wrappers are transparent to existing code: they preserve the original
 * fetch and EventSource APIs, only adding bookkeeping around them.
 */

const SLOW_THRESHOLD_MS = 3000;          // warn if a single fetch is pending this long
const SATURATION_THRESHOLD = 5;          // warn if total connections >= this (HTTP/1.1 pool is 6)
const PERIODIC_SCAN_MS = 5000;           // every 5s, list anything still pending past SLOW_THRESHOLD

const inflight = new Map();              // id → { url, startedAt }
const eventSources = new Map();          // id → { url, openedAt }
let nextId = 0;

function _saturationCheck() {
  const total = inflight.size + eventSources.size;
  if (total >= SATURATION_THRESHOLD) {
    console.warn(
      `[netDebug] ${total} concurrent connections — ` +
      `${eventSources.size} SSE + ${inflight.size} fetch. ` +
      `Browser HTTP/1.1 cap is ~6 per origin; new requests will queue.`
    );
  }
}

// ── fetch wrapper ────────────────────────────────────────
const origFetch = window.fetch.bind(window);

window.fetch = async function instrumentedFetch(input, init) {
  const id = ++nextId;
  const url = typeof input === 'string' ? input : (input && input.url) || String(input);
  const entry = { url, startedAt: performance.now() };
  inflight.set(id, entry);
  _saturationCheck();

  const slowTimer = setTimeout(() => {
    console.warn(
      `[netDebug] fetch still pending after ${SLOW_THRESHOLD_MS}ms — ` +
      `connection pool may be saturated. URL: ${url}`
    );
  }, SLOW_THRESHOLD_MS);

  try {
    return await origFetch(input, init);
  } finally {
    clearTimeout(slowTimer);
    inflight.delete(id);
  }
};

// ── EventSource wrapper ──────────────────────────────────
const OrigEventSource = window.EventSource;

function InstrumentedEventSource(url, options) {
  const id = ++nextId;
  const entry = { url: String(url), openedAt: performance.now() };
  eventSources.set(id, entry);
  _saturationCheck();

  const es = new OrigEventSource(url, options);
  const origClose = es.close.bind(es);
  es.close = function close() {
    eventSources.delete(id);
    origClose();
  };
  return es;
}
// Preserve readyState constants and prototype chain so callers see the same shape
InstrumentedEventSource.CONNECTING = OrigEventSource.CONNECTING;
InstrumentedEventSource.OPEN = OrigEventSource.OPEN;
InstrumentedEventSource.CLOSED = OrigEventSource.CLOSED;
InstrumentedEventSource.prototype = OrigEventSource.prototype;
window.EventSource = InstrumentedEventSource;

// ── On-demand snapshot ───────────────────────────────────
window.__netDebug = function dump() {
  /* eslint-disable no-console */
  console.group('[netDebug] snapshot');
  console.log(`Open EventSources: ${eventSources.size}`);
  for (const [id, e] of eventSources) {
    console.log(`  #${id} ${e.url}  (open ${Math.round(performance.now() - e.openedAt)}ms)`);
  }
  console.log(`In-flight fetches: ${inflight.size}`);
  for (const [id, e] of inflight) {
    console.log(`  #${id} ${e.url}  (pending ${Math.round(performance.now() - e.startedAt)}ms)`);
  }
  console.groupEnd();
  /* eslint-enable no-console */
  return { eventSources: eventSources.size, fetches: inflight.size };
};

// ── Periodic scan for hung requests ──────────────────────
setInterval(() => {
  const slow = [];
  for (const [id, e] of inflight) {
    const elapsed = performance.now() - e.startedAt;
    if (elapsed > SLOW_THRESHOLD_MS) {
      slow.push({ id, url: e.url, elapsedMs: Math.round(elapsed) });
    }
  }
  if (slow.length) {
    console.warn(`[netDebug] ${slow.length} fetch(es) pending > ${SLOW_THRESHOLD_MS}ms:`, slow);
  }
}, PERIODIC_SCAN_MS);

// eslint-disable-next-line no-console
console.log('[netDebug] active — call window.__netDebug() to dump state.');
