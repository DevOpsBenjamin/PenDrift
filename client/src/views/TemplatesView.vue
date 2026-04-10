<template>
  <div class="flex-1 max-w-5xl mx-auto px-4 sm:px-6 py-6 sm:py-10 w-full">
    <div class="flex items-center justify-between mb-6 sm:mb-8">
      <h1 class="font-body text-2xl sm:text-3xl font-bold">Templates</h1>
      <button
        class="px-4 py-2.5 bg-accent rounded-lg text-white text-sm font-semibold cursor-pointer
               hover:bg-accent-hover transition-colors active:scale-95"
        @click="startNew"
      >+ New Template</button>
    </div>

    <div class="flex flex-col md:flex-row gap-6">
      <!-- Template list -->
      <aside class="md:w-60 md:min-w-60 flex md:flex-col gap-2 overflow-x-auto md:overflow-x-visible pb-2 md:pb-0">
        <div
          v-for="tpl in store.templates"
          :key="tpl.id"
          class="group flex items-center justify-between gap-2 px-3 py-2 rounded-lg cursor-pointer text-sm whitespace-nowrap
                 transition-all duration-150"
          :class="editing?.id === tpl.id
            ? 'bg-bg-surface text-text-primary font-medium'
            : 'text-text-secondary hover:bg-bg-surface/50'"
          @click="edit(tpl)"
        >
          <span class="truncate">{{ tpl.name }}</span>
          <button
            class="opacity-0 group-hover:opacity-100 text-text-muted hover:text-accent transition-all shrink-0"
            @click.stop="duplicate(tpl)"
            title="Duplicate"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </button>
        </div>
      </aside>

      <!-- Editor -->
      <div v-if="editing" class="flex-1 flex flex-col gap-4 max-h-[calc(100dvh-200px)] overflow-y-auto pr-1">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">ID</label>
            <input v-model="editing.id" :disabled="!isNew"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors disabled:opacity-40" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Name</label>
            <input v-model="editing.name"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
        </div>

        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Description</label>
          <textarea v-model="editing.description" rows="2"
            class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   resize-y focus:outline-none focus:border-accent transition-colors"></textarea>
        </div>

        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Scenario</label>
          <textarea v-model="editing.scenario" rows="3"
            class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   resize-y focus:outline-none focus:border-accent transition-colors"></textarea>
        </div>

        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Style Instructions</label>
          <textarea v-model="editing.systemPromptAdditions" rows="3"
            class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   resize-y focus:outline-none focus:border-accent transition-colors"></textarea>
        </div>

        <!-- Variables section -->
        <div class="pt-4 border-t border-border-subtle">
          <div class="flex items-center gap-3 mb-1">
            <h3 class="text-sm font-semibold">Variables</h3>
            <button
              class="text-xs px-2.5 py-1 border border-dashed border-border rounded-md text-text-muted
                     hover:border-accent/40 hover:text-accent transition-all cursor-pointer"
              @click="addVariable"
            >+ Add</button>
          </div>
          <p class="text-xs text-text-muted mb-3">Use &#123;&#123;key&#125;&#125; anywhere in the template. Values are resolved before sending to the LLM.</p>

          <div
            v-for="(val, key) in editing.variables"
            :key="key"
            class="flex gap-2 items-center mb-2"
          >
            <span class="text-xs text-text-muted font-mono w-28 shrink-0 truncate">&#123;&#123;{{ key }}&#125;&#125;</span>
            <input
              :value="val"
              @input="editing.variables[key] = $event.target.value"
              class="flex-1 px-3 py-1.5 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors"
            />
            <button
              class="text-text-muted hover:text-accent transition-colors p-1"
              @click="deleteVariable(key)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <!-- User character -->
        <div class="pt-4 border-t border-border-subtle">
          <h3 class="text-sm font-semibold mb-3">User Character</h3>
          <div class="bg-bg-secondary rounded-xl p-4 flex flex-col gap-3 border border-accent-soft">
            <div class="flex flex-col gap-1.5">
              <label class="text-xs text-text-muted">Description</label>
              <textarea v-model="editing.userCharacter.description" rows="2"
                class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                       resize-y focus:outline-none focus:border-accent transition-colors"></textarea>
            </div>
            <div class="flex flex-col gap-1.5">
              <label class="text-xs text-text-muted">Initial State</label>
              <input v-model="editing.userCharacter.initialState"
                class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                       focus:outline-none focus:border-accent transition-colors" />
            </div>
          </div>
        </div>

        <!-- Characters section -->
        <div class="pt-4 border-t border-border-subtle">
          <div class="flex items-center gap-3 mb-3">
            <h3 class="text-sm font-semibold">Characters</h3>
            <button
              class="text-xs px-2.5 py-1 border border-dashed border-border rounded-md text-text-muted
                     hover:border-accent/40 hover:text-accent transition-all cursor-pointer"
              @click="addCharacter"
            >+ Add</button>
          </div>

          <div
            v-for="(char, i) in editing.characters"
            :key="i"
            class="bg-bg-secondary rounded-xl p-4 mb-3 flex flex-col gap-3 border border-border-subtle"
          >
            <div class="flex gap-3 items-end">
              <div class="flex-1 flex flex-col gap-1.5">
                <label class="text-xs text-text-muted">Name</label>
                <input v-model="char.name"
                  class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                         focus:outline-none focus:border-accent transition-colors" />
              </div>
              <button
                class="text-text-muted hover:text-accent transition-colors p-1 mb-1"
                @click="editing.characters.splice(i, 1)"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div class="flex flex-col gap-1.5">
              <label class="text-xs text-text-muted">Description</label>
              <textarea v-model="char.description" rows="3"
                class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                       resize-y focus:outline-none focus:border-accent transition-colors"></textarea>
            </div>
            <div class="flex flex-col gap-1.5">
              <label class="text-xs text-text-muted">Initial State</label>
              <input v-model="char.initialState"
                class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                       focus:outline-none focus:border-accent transition-colors" />
            </div>
          </div>
        </div>

        <!-- Masked Intents section -->
        <div class="pt-4 border-t border-border-subtle">
          <div class="flex items-center gap-3 mb-3">
            <h3 class="text-sm font-semibold">Masked Intents</h3>
            <button
              class="text-xs px-2.5 py-1 border border-dashed border-border rounded-md text-text-muted
                     hover:border-accent/40 hover:text-accent transition-all cursor-pointer"
              @click="editing.maskedIntents.push('')"
            >+ Add</button>
          </div>

          <div
            v-for="(_, i) in editing.maskedIntents"
            :key="i"
            class="flex gap-2 items-start mb-2"
          >
            <textarea v-model="editing.maskedIntents[i]" rows="2"
              class="flex-1 px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     resize-y focus:outline-none focus:border-accent transition-colors"></textarea>
            <button
              class="text-text-muted hover:text-accent transition-colors p-1 mt-1.5"
              @click="editing.maskedIntents.splice(i, 1)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <div class="flex justify-between pt-4 pb-2 sticky bottom-0 bg-bg-base/80 backdrop-blur-sm">
          <button
            v-if="!isNew"
            class="px-4 py-2 border border-error/30 rounded-lg text-error text-sm
                   hover:bg-error/10 transition-all cursor-pointer"
            @click="remove(editing.id)"
          >Delete</button>
          <span v-else></span>
          <div class="flex gap-3">
            <button
              class="px-4 py-2 border border-border rounded-lg text-text-secondary text-sm
                     hover:bg-bg-surface hover:text-text-primary transition-all cursor-pointer"
              @click="editing = null"
            >Cancel</button>
            <button
              class="px-5 py-2 bg-accent rounded-lg text-white text-sm font-semibold
                     hover:bg-accent-hover transition-colors cursor-pointer active:scale-95"
              @click="save"
            >Save</button>
          </div>
        </div>
      </div>

      <div v-else class="flex-1 flex items-center justify-center text-text-muted italic text-sm py-20">
        Select a template to edit or create a new one.
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { useSettingsStore } from '../stores/settings.js';

const store = useSettingsStore();
const editing = ref(null);
const isNew = ref(false);

onMounted(() => store.fetchTemplates());

function edit(tpl) {
  editing.value = JSON.parse(JSON.stringify(tpl));
  if (!editing.value.variables) editing.value.variables = {};
  if (!editing.value.characters) editing.value.characters = [];
  if (!editing.value.maskedIntents) editing.value.maskedIntents = [];
  if (!editing.value.userCharacter) editing.value.userCharacter = { name: '{{user}}', description: '', initialState: '' };
  isNew.value = false;
}

function duplicate(tpl) {
  const copy = JSON.parse(JSON.stringify(tpl));
  copy.id = copy.id + '_copy';
  copy.name = copy.name + ' (copy)';
  if (!copy.variables) copy.variables = {};
  if (!copy.characters) copy.characters = [];
  if (!copy.maskedIntents) copy.maskedIntents = [];
  if (!copy.userCharacter) copy.userCharacter = { name: '{{user}}', description: '', initialState: '' };
  editing.value = copy;
  isNew.value = true;
}

function startNew() {
  isNew.value = true;
  editing.value = {
    id: '',
    name: '',
    description: '',
    scenario: '',
    systemPromptAdditions: '',
    variables: { user: '' },
    userCharacter: { name: '{{user}}', description: '', initialState: '' },
    characters: [],
    maskedIntents: [],
  };
}

function addVariable() {
  const key = window.prompt('Variable name (no spaces, e.g. "city"):');
  if (!key || !key.trim()) return;
  const clean = key.trim().replace(/\s+/g, '_');
  if (editing.value.variables[clean] !== undefined) return;
  editing.value.variables[clean] = '';
}

function deleteVariable(key) {
  delete editing.value.variables[key];
}

function addCharacter() {
  editing.value.characters.push({ name: '', description: '', initialState: '' });
}

async function save() {
  if (!editing.value.id || !editing.value.name) return;
  editing.value.maskedIntents = editing.value.maskedIntents.filter(i => i.trim());
  const saved = await store.saveTemplate(editing.value);
  if (saved) {
    editing.value = JSON.parse(JSON.stringify(saved));
    isNew.value = false;
  }
}

async function remove(id) {
  if (window.confirm('Delete this template?')) {
    await store.deleteTemplate(id);
    if (editing.value?.id === id) editing.value = null;
  }
}
</script>
