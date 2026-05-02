<template>
  <div class="flex-1 overflow-y-auto px-4 sm:px-8 lg:px-12 py-6 sm:py-10 relative" ref="container" @scroll="checkScrollPosition">
    <div class="max-w-2xl mx-auto">
      <div v-if="chunks.length === 0 && store.streamPhase === 'idle'" class="text-center py-20 sm:py-32">
        <p class="text-text-secondary text-lg italic">The story hasn't begun yet.</p>
        <p class="text-text-muted text-sm mt-2">Write a directive below to start.</p>
      </div>

      <template v-for="(chunk, i) in chunks" :key="chunk.id">
        <ChunkBlock
          :chunk="chunk"
          :chunkIndex="i"
          :isLast="i === chunks.length - 1"
          :finalized="finalized"
          @regenerate="(data) => $emit('regenerate', data)"
          @delete="(chunkId) => $emit('delete', chunkId)"
          @edit="$emit('edit', $event)"
          @switchVersion="$emit('switchVersion', $event)"
        />
        <MetaMarker
          v-for="entry in metaMarkersAfter(chunk.id)"
          :key="`meta-${chunk.id}-${entry.timestamp}`"
          :entry="entry"
        />
      </template>

      <!-- Preparing phase: backend is doing prep work (loading settings, building messages) -->
      <div v-if="store.streamPhase === 'preparing'"
        class="my-6 p-5 bg-bg-surface/50 rounded-xl border border-border-subtle flex items-center gap-3">
        <div class="flex gap-1">
          <span class="w-2 h-2 bg-text-muted rounded-full animate-bounce" style="animation-delay: 0ms"></span>
          <span class="w-2 h-2 bg-text-muted rounded-full animate-bounce" style="animation-delay: 150ms"></span>
          <span class="w-2 h-2 bg-text-muted rounded-full animate-bounce" style="animation-delay: 300ms"></span>
        </div>
        <div class="flex-1">
          <div class="text-sm font-semibold text-text-primary">Preparing…</div>
          <div class="text-xs text-text-muted">Loading session context and building the prompt.</div>
        </div>
        <button
          class="text-xs px-2 py-0.5 border border-error/40 text-error rounded hover:bg-error/10 transition-colors cursor-pointer"
          @click="store.cancelStream()"
        >Stop</button>
      </div>

      <!-- Meta-analysis phase: a separate LLM call running between chunks to update characters/facts -->
      <div v-if="store.streamPhase === 'meta_running'"
        class="my-6 p-5 bg-bg-surface/50 rounded-xl border border-purple-500/40 flex items-center gap-3">
        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-purple-400 animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-opacity="0.3" stroke-width="3" />
          <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
        </svg>
        <div class="flex-1">
          <div class="text-sm font-semibold text-purple-300">Running meta-analysis…</div>
          <div class="text-xs text-text-muted">Updating character sheets and trimming the facts list before the next chunk. This is a separate LLM call — the actual narrative will start streaming after.</div>
        </div>
        <button
          class="text-xs px-2 py-0.5 border border-error/40 text-error rounded hover:bg-error/10 transition-colors cursor-pointer"
          @click="store.cancelStream()"
        >Stop</button>
      </div>

      <!-- Meta done summary (briefly visible between meta_running and the streaming) -->
      <div v-if="store.metaSummary && (store.streamPhase === 'preparing' || store.streamPhase === 'thinking')"
        class="my-3 px-4 py-2 bg-purple-500/10 border border-purple-500/30 rounded-lg text-xs text-purple-300 flex items-center gap-3">
        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
        </svg>
        <span>
          Meta-analysis complete:
          {{ store.metaSummary.charactersUpdated }} char update<span v-if="store.metaSummary.charactersUpdated !== 1">s</span>,
          {{ store.metaSummary.newCharacters }} new,
          {{ store.metaSummary.factsCount }} facts kept<span v-if="store.metaSummary.consistencyFlags">, {{ store.metaSummary.consistencyFlags }} flag<span v-if="store.metaSummary.consistencyFlags !== 1">s</span></span>.
        </span>
      </div>

      <!-- Loading model phase: shown when no model is loaded and we're auto-loading from preset -->
      <div v-if="store.streamPhase === 'loading_model'"
        class="my-6 p-5 bg-bg-surface/50 rounded-xl border border-accent/30 flex items-center gap-3">
        <div class="flex gap-1">
          <span class="w-2 h-2 bg-accent rounded-full animate-bounce" style="animation-delay: 0ms"></span>
          <span class="w-2 h-2 bg-accent rounded-full animate-bounce" style="animation-delay: 150ms"></span>
          <span class="w-2 h-2 bg-accent rounded-full animate-bounce" style="animation-delay: 300ms"></span>
        </div>
        <div class="flex-1">
          <div class="text-sm font-semibold text-text-primary">Loading model…</div>
          <div class="text-xs text-text-muted font-mono truncate" :title="store.modelLoadingPath">{{ shortPath(store.modelLoadingPath) }}</div>
        </div>
        <button
          class="text-xs px-2 py-0.5 border border-error/40 text-error rounded hover:bg-error/10 transition-colors cursor-pointer"
          @click="store.cancelStream()"
        >Stop</button>
      </div>

      <!-- Live streaming block — replaces the bouncing dots when streaming -->
      <div v-if="store.streamPhase === 'thinking' || store.streamPhase === 'narrative'"
        class="my-6 p-5 bg-bg-surface/50 rounded-xl border border-accent/30 relative">
        <div class="flex items-center gap-2 mb-3">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-accent animate-pulse"
            fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round"
              d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          <span class="text-xs uppercase tracking-wider text-accent font-semibold">
            {{ store.streamPhase === 'thinking' ? 'Thinking…' : 'Writing narrative' }}
          </span>
          <button
            class="ml-auto text-xs px-2 py-0.5 border border-error/40 text-error rounded hover:bg-error/10 transition-colors cursor-pointer"
            @click="store.cancelStream()"
            title="Stop generation"
          >Stop</button>
        </div>

        <!-- Thinking phase: show thinking text live -->
        <pre v-if="store.streamPhase === 'thinking'"
          class="text-xs text-text-muted font-ui whitespace-pre-wrap break-words leading-relaxed max-h-64 overflow-y-auto"
          ref="thinkingScroll"
        >{{ store.liveThinking || '…' }}<span class="inline-block w-2 h-3 bg-accent/60 align-middle animate-pulse"></span></pre>

        <!-- Narrative phase: thinking collapsed at top, narrative streams below -->
        <template v-else>
          <details class="mb-3 text-xs">
            <summary class="cursor-pointer text-text-muted hover:text-text-secondary">
              💭 Thinking ({{ store.liveThinking.length }} chars)
            </summary>
            <pre class="mt-2 p-2 bg-bg-primary/50 rounded text-text-muted whitespace-pre-wrap break-words font-ui leading-relaxed max-h-48 overflow-y-auto">{{ store.liveThinking }}</pre>
          </details>
          <div class="text-text-primary font-ui leading-relaxed break-words narrative-content" ref="narrativeScroll">
            <span v-html="liveNarrativeHtml"></span><span class="inline-block w-2 h-4 bg-accent/60 align-middle animate-pulse"></span>
          </div>
        </template>
      </div>

      <!-- Bouncing dots for the prep / pre-stream phase -->
      <div v-else-if="generating" class="flex gap-1.5 py-6 justify-center">
        <span class="w-2 h-2 bg-accent rounded-full animate-bounce" style="animation-delay: 0ms"></span>
        <span class="w-2 h-2 bg-accent rounded-full animate-bounce" style="animation-delay: 150ms"></span>
        <span class="w-2 h-2 bg-accent rounded-full animate-bounce" style="animation-delay: 300ms"></span>
      </div>
    </div>

    <!-- Jump-to-bottom button — shown when user scrolled up during streaming -->
    <button
      v-if="showJumpButton"
      class="sticky bottom-4 ml-auto mr-4 sm:mr-8 lg:mr-12 px-3 py-2 bg-accent text-white text-xs rounded-full
             shadow-lg hover:bg-accent-hover transition-colors cursor-pointer flex items-center gap-1.5 self-end"
      @click="jumpToBottom"
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
        <path stroke-linecap="round" stroke-linejoin="round" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
      </svg>
      Jump to live
    </button>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue';
import ChunkBlock from './ChunkBlock.vue';
import MetaMarker from './MetaMarker.vue';
import { useNarrativeStore } from '../../stores/narrative.js';
import { renderNarrative } from '../../utils/narrative-renderer.js';

const props = defineProps({
  chunks: Array,
  generating: Boolean,
  finalized: Boolean,
});

defineEmits(['regenerate', 'delete', 'edit', 'switchVersion']);

const store = useNarrativeStore();
const container = ref(null);
const thinkingScroll = ref(null);
const narrativeScroll = ref(null);

// Group meta-history entries by the last chunk they analyzed (chunkRange.to),
// so we can render a divider right AFTER that chunk in the timeline.
const metaByChunkId = computed(() => {
  const map = new Map();
  for (const entry of (store.metaHistory || [])) {
    const id = entry.chunkRange?.to;
    if (!id) continue;
    if (!map.has(id)) map.set(id, []);
    map.get(id).push(entry);
  }
  return map;
});
function metaMarkersAfter(chunkId) {
  return metaByChunkId.value.get(chunkId) || [];
}

// Render the live narrative as markdown — re-parses on every token but markdown-it
// is cheap (~ms for a few KB) and the visual payoff of formatted prose during
// streaming is worth it. Same renderer as the finalized chunks for consistency.
const liveNarrativeHtml = computed(() => {
  if (!store.liveNarrative) return '';
  try {
    return renderNarrative(store.liveNarrative);
  } catch {
    return store.liveNarrative;  // fallback if markdown chokes on partial input
  }
});

// Threshold in px — if the user is within this distance from the bottom we
// consider them "following along" and keep auto-scrolling. Otherwise we don't
// fight their manual scroll position.
const FOLLOW_THRESHOLD = 80;

function isAtBottom(el) {
  if (!el) return true;
  return el.scrollHeight - el.scrollTop - el.clientHeight < FOLLOW_THRESHOLD;
}

function scrollToBottomIfFollowing(el) {
  if (!el) return;
  if (isAtBottom(el)) {
    el.scrollTop = el.scrollHeight;
  }
}

watch(() => props.chunks.length, async () => {
  const wasFollowing = isAtBottom(container.value);
  await nextTick();
  if (wasFollowing && container.value) {
    container.value.scrollTop = container.value.scrollHeight;
  }
});

// Auto-scroll the live thinking/narrative panes as text streams in,
// but only if the user hasn't manually scrolled away.
watch(() => store.liveThinking, async () => {
  const innerFollowing = isAtBottom(thinkingScroll.value);
  const outerFollowing = isAtBottom(container.value);
  await nextTick();
  if (innerFollowing && thinkingScroll.value) {
    thinkingScroll.value.scrollTop = thinkingScroll.value.scrollHeight;
  }
  if (outerFollowing && container.value) {
    container.value.scrollTop = container.value.scrollHeight;
  }
});
watch(() => store.liveNarrative, async () => {
  const wasFollowing = isAtBottom(container.value);
  await nextTick();
  if (wasFollowing && container.value) {
    container.value.scrollTop = container.value.scrollHeight;
  }
});

// "Jump to bottom" button shown when the user has scrolled away during streaming
const showJumpButton = ref(false);
function checkScrollPosition() {
  const streaming = store.streamPhase === 'thinking' || store.streamPhase === 'narrative';
  showJumpButton.value = streaming && !isAtBottom(container.value);
}
watch(() => store.streamPhase, checkScrollPosition);
function jumpToBottom() {
  if (container.value) container.value.scrollTop = container.value.scrollHeight;
  showJumpButton.value = false;
}

function shortPath(p) {
  if (!p) return '';
  return p.split(/[\\/]/).pop();
}
</script>
