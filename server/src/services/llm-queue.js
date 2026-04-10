/**
 * Global LLM call queue. Only one call runs at a time.
 * Others wait in line.
 */

const queue = [];
let running = false;
let jobCounter = 0;

export function enqueueLLMCall(fn, label) {
  return new Promise((resolve, reject) => {
    jobCounter++;
    const id = jobCounter;
    const tag = label || `job#${id}`;
    queue.push({ fn, resolve, reject, tag });
    console.log(`[LLM Queue] +++ Added "${tag}" | Queue: ${queue.length} waiting, ${running ? '1 running' : 'idle'}`);
    processQueue();
  });
}

async function processQueue() {
  if (running || queue.length === 0) return;

  running = true;
  const { fn, resolve, reject, tag } = queue.shift();
  console.log(`[LLM Queue] >>> Starting "${tag}" | ${queue.length} still waiting`);

  const start = Date.now();
  try {
    const result = await fn();
    const duration = ((Date.now() - start) / 1000).toFixed(1);
    console.log(`[LLM Queue] <<< Done "${tag}" in ${duration}s | ${queue.length} waiting`);
    resolve(result);
  } catch (err) {
    const duration = ((Date.now() - start) / 1000).toFixed(1);
    console.log(`[LLM Queue] !!! Failed "${tag}" in ${duration}s: ${err.message} | ${queue.length} waiting`);
    reject(err);
  } finally {
    running = false;
    processQueue();
  }
}

export function getQueueLength() {
  return queue.length + (running ? 1 : 0);
}
