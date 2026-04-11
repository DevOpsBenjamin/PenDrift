<template>
  <div class="p-3 border-t border-border-subtle">
    <h3 class="text-[11px] font-semibold uppercase tracking-widest text-text-muted mb-3 flex items-center gap-2">
      Characters
      <span
        v-if="updating"
        class="text-[10px] normal-case tracking-normal text-accent font-normal animate-pulse"
      >Analyzing...</span>
    </h3>
    <div v-if="characters.length === 0" class="text-xs text-text-muted italic">
      No characters yet
    </div>
    <ul class="space-y-1">
      <li
        v-for="char in characters"
        :key="char.name"
        class="flex items-center justify-between px-2 py-1.5 rounded-md text-sm text-text-secondary
               hover:bg-bg-surface/50 transition-all"
      >
        <span class="truncate">{{ char.name }}</span>
        <button
          class="text-text-muted hover:text-accent transition-colors shrink-0 p-0.5"
          @click="requestInspect(char)"
          title="View/edit character sheet"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            <path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
          </svg>
        </button>
      </li>
    </ul>

    <!-- Add character button -->
    <button
      class="w-full mt-2 py-1.5 text-xs text-text-muted hover:text-text-secondary hover:bg-bg-surface/50
             rounded-lg transition-all cursor-pointer border border-dashed border-border"
      @click="addCharacter"
    >+ Add Character</button>

    <!-- Facts button -->
    <button
      class="w-full mt-1 py-1.5 text-xs text-text-muted hover:text-text-secondary hover:bg-bg-surface/50
             rounded-lg transition-all cursor-pointer"
      @click="$emit('editFacts')"
    >Established Facts</button>

    <!-- Consistency warnings -->
    <div v-if="flags.length" class="mt-3 space-y-1">
      <h4 class="text-[10px] font-semibold uppercase tracking-wider text-warning mb-1">Flags</h4>
      <p
        v-for="(flag, i) in flags"
        :key="i"
        class="text-[10px] text-warning/80 leading-relaxed bg-warning/5 rounded px-2 py-1"
      >{{ flag }}</p>
    </div>

    <!-- Spoiler warning -->
    <Teleport to="body">
      <div
        v-if="showWarning"
        class="fixed inset-0 bg-bg-overlay backdrop-blur-sm flex items-center justify-center z-50 p-4"
        @click.self="showWarning = false"
      >
        <div class="bg-bg-secondary border border-border rounded-2xl p-6 w-full max-w-sm shadow-2xl text-center">
          <div class="text-warning text-3xl mb-3">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-10 h-10 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h3 class="text-base font-semibold mb-2">Spoiler Warning</h3>
          <p class="text-sm text-text-secondary mb-5">Character sheets may reveal hidden plot details, secret motivations, and narrative twists.</p>
          <div class="flex justify-center gap-3">
            <button
              class="px-4 py-2 border border-border rounded-lg text-text-secondary text-sm
                     hover:bg-bg-surface hover:text-text-primary transition-all cursor-pointer"
              @click="showWarning = false"
            >Cancel</button>
            <button
              class="px-5 py-2 bg-accent rounded-lg text-white text-sm font-semibold
                     hover:bg-accent-hover transition-colors cursor-pointer"
              @click="confirmInspect"
            >Show me</button>
          </div>
        </div>
      </div>

      <!-- Character sheet edit popup -->
      <div
        v-if="editing"
        class="fixed inset-0 bg-bg-overlay backdrop-blur-sm flex items-center justify-center z-50 p-4"
        @click.self="editing = null"
      >
        <div class="bg-bg-secondary border border-border rounded-2xl p-6 w-full max-w-md shadow-2xl max-h-[80vh] overflow-y-auto">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-lg font-semibold text-accent">{{ editing.name }}</h2>
            <button
              class="text-text-muted hover:text-text-primary transition-colors p-1"
              @click="editing = null"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div class="space-y-4">
            <div>
              <label class="text-[11px] font-semibold uppercase tracking-wider text-text-muted mb-1 block">Current State</label>
              <textarea v-model="editing.currentState" rows="3"
                class="w-full px-3 py-2 bg-bg-primary border border-border rounded-lg text-sm text-text-primary
                       resize-y focus:outline-none focus:border-accent transition-colors"></textarea>
            </div>

            <div>
              <label class="text-[11px] font-semibold uppercase tracking-wider text-text-muted mb-1 block">Traits (one per line)</label>
              <textarea v-model="traitsText" rows="3"
                class="w-full px-3 py-2 bg-bg-primary border border-border rounded-lg text-sm text-text-primary
                       resize-y focus:outline-none focus:border-accent transition-colors"></textarea>
            </div>

            <div>
              <label class="text-[11px] font-semibold uppercase tracking-wider text-text-muted mb-1 block">Key Events (one per line)</label>
              <textarea v-model="eventsText" rows="4"
                class="w-full px-3 py-2 bg-bg-primary border border-border rounded-lg text-sm text-text-primary
                       resize-y focus:outline-none focus:border-accent transition-colors"></textarea>
            </div>

            <div v-if="editing.lastUpdated" class="text-[10px] text-text-muted">
              Last updated: {{ new Date(editing.lastUpdated).toLocaleString() }}
            </div>

            <div class="flex justify-end gap-3 pt-2">
              <button
                class="px-4 py-2 border border-border rounded-lg text-text-secondary text-sm
                       hover:bg-bg-surface hover:text-text-primary transition-all cursor-pointer"
                @click="editing = null"
              >Cancel</button>
              <button
                class="px-5 py-2 bg-accent rounded-lg text-white text-sm font-semibold
                       hover:bg-accent-hover transition-colors cursor-pointer"
                @click="saveCharacter"
              >Save</button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue';

const props = defineProps({
  characters: Array,
  updating: Boolean,
  flags: { type: Array, default: () => [] },
});

const emit = defineEmits(['editFacts', 'saveCharacter', 'addCharacter']);

const showWarning = ref(false);
const pendingChar = ref(null);
const editing = ref(null);

const traitsText = computed({
  get: () => (editing.value?.traits || []).join('\n'),
  set: (val) => { if (editing.value) editing.value.traits = val.split('\n').map(s => s.trim()).filter(Boolean); },
});

const eventsText = computed({
  get: () => (editing.value?.keyEvents || []).join('\n'),
  set: (val) => { if (editing.value) editing.value.keyEvents = val.split('\n').map(s => s.trim()).filter(Boolean); },
});

function requestInspect(char) {
  pendingChar.value = char;
  showWarning.value = true;
}

function confirmInspect() {
  showWarning.value = false;
  editing.value = JSON.parse(JSON.stringify(pendingChar.value));
  pendingChar.value = null;
}

function saveCharacter() {
  editing.value.lastUpdated = new Date().toISOString();
  emit('saveCharacter', editing.value);
  editing.value = null;
}

function addCharacter() {
  const name = window.prompt('Character name:');
  if (!name?.trim()) return;
  editing.value = {
    name: name.trim(),
    currentState: '',
    traits: [],
    keyEvents: [],
    lastUpdated: new Date().toISOString(),
    _isNew: true,
  };
}
</script>
