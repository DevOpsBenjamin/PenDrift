/**
 * Global LLM call queue. Only one call runs at a time.
 * Others wait in line.
 */

const queue = [];
let running = false;

export function enqueueLLMCall(fn) {
  return new Promise((resolve, reject) => {
    queue.push({ fn, resolve, reject });
    processQueue();
  });
}

async function processQueue() {
  if (running || queue.length === 0) return;

  running = true;
  const { fn, resolve, reject } = queue.shift();

  try {
    const result = await fn();
    resolve(result);
  } catch (err) {
    reject(err);
  } finally {
    running = false;
    processQueue();
  }
}

export function getQueueLength() {
  return queue.length + (running ? 1 : 0);
}
