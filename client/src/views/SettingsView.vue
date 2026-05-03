<template>
  <div class="flex-1 max-w-5xl mx-auto px-4 sm:px-6 py-6 sm:py-10 w-full">

    <!-- LLM Engine Panel (slim: version + exe + status) -->
    <div class="mb-8 p-5 bg-bg-surface rounded-xl border border-border">
      <h2 class="font-body text-lg font-bold mb-4">LLM Engine</h2>

      <div class="flex items-center gap-3 mb-4 p-3 bg-bg-primary rounded-lg border border-border-subtle">
        <div class="flex-1">
          <div class="text-sm text-text-primary font-medium">llama-server</div>
          <div class="text-xs text-text-muted mt-0.5">
            <template v-if="llmVersionInfo.installed">
              Installed: <span class="font-mono text-text-secondary">{{ llmVersionInfo.installed.tag }}</span>
              ({{ llmVersionInfo.installed.variant }})
              <span v-if="llmVersionInfo.updateAvailable" class="text-accent ml-1">— update available: {{ llmVersionInfo.latest }}</span>
            </template>
            <template v-else>Not installed</template>
          </div>
        </div>
        <select v-model="llmVariant" class="px-2 py-1.5 bg-bg-surface border border-border rounded text-xs text-text-secondary">
          <option value="cuda13">CUDA 13.1 (RTX 50xx+)</option>
          <option value="cuda12">CUDA 12.4 (older cards)</option>
          <option value="cpu">CPU only</option>
        </select>
        <button
          class="px-4 py-1.5 bg-accent rounded-lg text-white text-xs font-semibold
                 hover:bg-accent-hover transition-colors cursor-pointer active:scale-95 whitespace-nowrap"
          :disabled="llmDownloading"
          @click="doDownload"
        >{{ llmDownloading ? 'Downloading...' : (llmVersionInfo.installed ? 'Update' : 'Download') }}</button>
      </div>

      <details class="mb-3">
        <summary class="text-xs text-text-muted cursor-pointer hover:text-text-secondary">Manual exe path (optional)</summary>
        <div class="flex gap-2 mt-2">
          <input v-model="llmExePath" placeholder="C:\llama.cpp\llama-server.exe"
            class="flex-1 px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm font-mono
                   focus:outline-none focus:border-accent transition-colors" />
          <button
            class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-secondary text-sm
                   hover:border-accent/40 hover:text-text-primary transition-all cursor-pointer whitespace-nowrap"
            :disabled="!llmExePath || llmConfiguring"
            @click="saveLlmExe"
          >{{ llmConfiguring ? '...' : 'Set' }}</button>
        </div>
      </details>

      <div class="flex items-center gap-2 text-sm">
        <span class="w-2.5 h-2.5 rounded-full" :class="llmStatus.running ? 'bg-green-400' : 'bg-text-muted/30'"></span>
        <span class="text-text-secondary">
          <template v-if="llmStatus.running">
            Loaded — <span class="font-mono text-xs">{{ shortModelName(llmStatus.modelPath) }}</span> on port {{ llmStatus.port }}
          </template>
          <template v-else>No model loaded</template>
        </span>
        <button
          v-if="llmStatus.running"
          class="ml-auto px-3 py-1 border border-border rounded text-xs text-text-secondary
                 hover:border-error/40 hover:text-error transition-all cursor-pointer"
          :disabled="llmLoading"
          @click="doUnload"
        >Unload</button>
      </div>
    </div>

    <!-- Settings Presets -->
    <div class="flex items-center justify-between mb-6 sm:mb-8">
      <h1 class="font-body text-2xl sm:text-3xl font-bold">Settings Presets</h1>
      <button
        class="px-4 py-2.5 bg-accent rounded-lg text-white text-sm font-semibold cursor-pointer
               hover:bg-accent-hover transition-colors active:scale-95"
        @click="startNew"
      >+ New Preset</button>
    </div>

    <div class="flex flex-col md:flex-row gap-6">
      <!-- Preset list -->
      <aside class="md:w-56 md:min-w-56 flex md:flex-col gap-2 overflow-x-auto md:overflow-x-visible pb-2 md:pb-0">
        <div
          v-for="preset in store.presets"
          :key="preset.id"
          class="group flex items-center justify-between gap-2 px-3 py-2 rounded-lg cursor-pointer text-sm whitespace-nowrap
                 transition-all duration-150"
          :class="editing?.id === preset.id
            ? 'bg-bg-surface text-text-primary font-medium'
            : 'text-text-secondary hover:bg-bg-surface/50'"
          @click="edit(preset)"
        >
          <span class="truncate flex items-center gap-1.5">
            <span v-if="preset.isDefault" class="text-accent" title="Default preset (used by Import, Rerun, Enrich)">★</span>
            {{ preset.name }}
          </span>
          <button
            class="opacity-0 group-hover:opacity-100 text-text-muted hover:text-accent transition-all shrink-0"
            @click.stop="duplicate(preset)"
            title="Duplicate"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </button>
        </div>
      </aside>

      <!-- Editor -->
      <div v-if="editing" class="flex-1 flex flex-col gap-4">
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

        <div class="flex flex-col gap-1.5 mt-2">
          <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Provider</label>
          <select v-model="editing.provider"
            class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm focus:outline-none focus:border-accent transition-colors">
            <option value="llama-server">llama.cpp (Local GGUF)</option>
            <option value="xai" :disabled="!providerStatus.xai">xAI {{ providerStatus.xai ? '' : '(Key not set in .env)' }}</option>
            <option value="openai" :disabled="!providerStatus.openai">OpenAI {{ providerStatus.openai ? '' : '(Key not set in .env)' }}</option>
          </select>
        </div>

        <!-- Local Model Loading -->
        <template v-if="editing.provider === 'llama-server'">
          <h3 class="text-xs text-text-muted font-semibold uppercase tracking-wider pt-3 border-t border-border-subtle">Model Loading</h3>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">GGUF Model Path</label>
            <div class="flex gap-2">
              <input v-model="editing.modelPath" placeholder="I:\models\qwen3.5-27b-q3.gguf"
                class="flex-1 px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm font-mono
                       focus:outline-none focus:border-accent transition-colors" />
              <button
                class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-secondary text-sm
                       hover:border-accent/40 hover:text-text-primary transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5"
                @click="showBrowser = true"
                title="Browse for a .gguf file"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
                </svg>
                Browse
              </button>
            </div>
          </div>

        <div class="grid grid-cols-3 gap-3">
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted">GPU Layers</label>
            <input v-model.number="editing.gpuLayers" type="number" min="0" max="999"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted">Context Size</label>
            <input v-model.number="editing.contextSize" type="number" step="1024" min="1024"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted">Port</label>
            <input v-model.number="editing.port" type="number" min="1024" max="65535"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
        </div>

          <div class="flex items-center gap-3">
            <button
              class="px-5 py-2.5 rounded-lg text-white text-sm font-semibold transition-all cursor-pointer active:scale-95"
              :class="isActivePreset && llmStatus.running
                ? 'bg-error hover:bg-error/80'
                : 'bg-accent hover:bg-accent-hover'"
              :disabled="llmLoading || (!llmVersionInfo.installed && !llmExePath) || !editing.modelPath"
              @click="isActivePreset && llmStatus.running ? doUnload() : doLoad()"
            >
              <span v-if="llmLoading">{{ llmLoadingText }}</span>
              <span v-else-if="isActivePreset && llmStatus.running">Unload Model</span>
              <span v-else>Load Model</span>
            </button>
            <span v-if="isActivePreset && llmStatus.running" class="text-xs text-green-400">● This preset is active</span>
            <span v-else-if="llmStatus.running" class="text-xs text-text-muted">Another model is loaded</span>
            <span v-if="llmError" class="text-sm text-error">{{ llmError }}</span>
          </div>
        </template>
        
        <!-- External API Configuration -->
        <template v-else-if="editing.provider === 'xai' || editing.provider === 'openai'">
          <h3 class="text-xs text-text-muted font-semibold uppercase tracking-wider pt-3 border-t border-border-subtle">API Configuration</h3>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
             <div class="flex flex-col gap-1.5">
               <label class="text-xs text-text-muted flex justify-between">
                 Model Name
                 <button class="text-accent hover:underline text-[10px]" @click="refreshModels" :disabled="fetchingModels">
                   {{ fetchingModels ? 'Fetching...' : 'Fetch List' }}
                 </button>
               </label>
               <input v-model="editing.providerConfig[editing.provider].model" :list="'models-list-' + editing.provider"
                 class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm focus:outline-none focus:border-accent transition-colors" />
               <datalist :id="'models-list-' + editing.provider">
                 <option v-for="m in remoteModels" :key="m" :value="m"></option>
               </datalist>
             </div>
             <div class="flex flex-col gap-1.5">
               <label class="text-xs text-text-muted">Base URL</label>
               <input v-model="editing.providerConfig[editing.provider].baseUrl"
                 class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm focus:outline-none focus:border-accent transition-colors" />
             </div>
          </div>
          <p class="text-xs text-text-muted">API Keys are securely read from the backend <code>.env</code> file. No keys are saved in this preset.</p>
        </template>

        <!-- Samplers -->
        <h3 class="text-xs text-text-muted font-semibold uppercase tracking-wider pt-3 border-t border-border-subtle">Samplers</h3>
        <div class="grid grid-cols-3 sm:grid-cols-4 gap-3">
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted">Temp</label>
            <input v-model.number="editing.temperature" type="number" step="0.1" min="0" max="2"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted">Top P</label>
            <input v-model.number="editing.topP" type="number" step="0.05" min="0" max="1"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted">Top K</label>
            <input v-model.number="editing.topK" type="number" step="1" min="0"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted">Min P</label>
            <input v-model.number="editing.minP" type="number" step="0.01" min="0" max="1"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted">Presence Pen.</label>
            <input v-model.number="editing.presencePenalty" type="number" step="0.1" min="-2" max="2"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted">Frequency Pen.</label>
            <input v-model.number="editing.frequencyPenalty" type="number" step="0.1" min="-2" max="2"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted">Repeat Pen.</label>
            <input v-model.number="editing.repeatPenalty" type="number" step="0.1" min="0" max="2"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted">Seed</label>
            <input v-model.number="editing.seed" type="number" step="1"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
        </div>

        <!-- Token Budget -->
        <h3 class="text-xs text-text-muted font-semibold uppercase tracking-wider pt-3 border-t border-border-subtle">Token Budget</h3>
        <div class="text-xs text-text-muted -mb-1 leading-relaxed">
          The first three caps apply ONLY to narrative generation (per-chunk) and sum to the narrative budget.
          <br />
          <span class="text-text-secondary">Max Tokens</span> is a separate ceiling used by meta (×2), templates (chub-import / enrich / rerun), and Ask-the-Narrator. Bump it high for cloud models like Grok — local models like Qwen may struggle past 4096.
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted" title="Per-chunk thinking budget for narrative generation only">Thinking <span class="text-text-muted/60">(narrative)</span></label>
            <input v-model.number="editing.thinkingTokens" type="number" step="100" min="0"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted" title="Per-chunk narrative prose budget">Narrative</label>
            <input v-model.number="editing.narrativeTokens" type="number" step="100" min="100"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted" title="Per-chunk suggestions budget">Suggestions</label>
            <input v-model.number="editing.suggestionTokens" type="number" step="50" min="0"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted" title="Ceiling for meta (×2), templates (chub-import / enrich / rerun) and Ask-the-Narrator. Independent from the narrative budgets above.">Max Tokens <span class="text-text-muted/60">(meta / templates / query)</span></label>
            <input v-model.number="editing.maxTokens" type="number" step="256" min="256"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
        </div>
        <p class="text-xs text-text-muted -mt-2">
          Narrative chunk budget: {{ (editing.thinkingTokens || 0) + (editing.narrativeTokens || 0) + (editing.suggestionTokens || 0) }} tokens
          (<span class="font-mono">{{ editing.thinkingTokens || 0 }} + {{ editing.narrativeTokens || 0 }} + {{ editing.suggestionTokens || 0 }}</span>).
          Meta / template / query calls use Max Tokens directly (or ×2 for meta).
        </p>

        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Recent Chunks Window</label>
          <input v-model.number="editing.chunkUpdateInterval" type="number" min="1"
            class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   focus:outline-none focus:border-accent transition-colors" />
          <p class="text-xs text-text-muted">
            How many recent chunks the model sees on each call (narrative, ask, etc.) — and the cadence at which meta-analysis re-runs over that same window.
          </p>
        </div>

        <h3 class="text-xs text-text-muted font-semibold uppercase tracking-wider pt-3 border-t border-border-subtle">Prompts</h3>
        <p class="text-xs text-text-muted -mt-2">
          System prompts ship with the app and update automatically. Tick "Override" on a prompt to customize it for this preset only.
        </p>
        <div v-for="p in promptsList" :key="p.name" class="flex flex-col gap-1.5">
          <div class="flex items-center justify-between gap-3">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">{{ promptLabel(p.name) }}</label>
            <label class="flex items-center gap-1.5 text-xs text-text-muted cursor-pointer select-none">
              <input
                type="checkbox"
                :checked="isOverridden(p.name)"
                @change="toggleOverride(p.name, $event.target.checked)"
                class="accent-accent cursor-pointer"
              />
              <span :class="isOverridden(p.name) ? 'text-accent' : ''">Override</span>
            </label>
          </div>
          <textarea
            v-if="isOverridden(p.name)"
            v-model="editing[overrideKey(p.name)]"
            rows="20"
            class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   font-ui resize-y min-h-32 focus:outline-none focus:border-accent transition-colors"
          ></textarea>
          <textarea
            v-else
            :value="systemPrompts[p.name] || ''"
            rows="20"
            readonly
            class="px-3 py-2 bg-bg-primary/50 border border-border-subtle rounded-lg text-text-muted text-sm
                   font-ui resize-y min-h-32 cursor-not-allowed"
            title="System default. Tick 'Override' to customize for this preset."
          ></textarea>
        </div>

        <div class="flex justify-between pt-2">
          <div class="flex gap-2">
            <button
              v-if="!isNew && editing.id !== 'default'"
              class="px-4 py-2 border border-error/30 rounded-lg text-error text-sm
                     hover:bg-error/10 transition-all cursor-pointer"
              @click="remove(editing.id)"
            >Delete</button>
            <button
              v-if="!isNew && !editing.isDefault"
              class="px-4 py-2 border border-border rounded-lg text-text-secondary text-sm
                     hover:border-accent/40 hover:text-accent transition-all cursor-pointer"
              @click="setAsDefault"
              title="Mark this preset as the default for Import, Rerun, Enrich"
            >★ Set as default</button>
            <span v-if="!isNew && editing.isDefault" class="self-center text-xs text-accent">★ Default preset</span>
          </div>
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
        Select a preset to edit or create a new one.
      </div>
    </div>

    <FileBrowserModal
      v-if="showBrowser"
      :initial-path="editing?.modelPath"
      @close="showBrowser = false"
      @select="onFileSelected"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue';
import { useSettingsStore } from '../stores/settings.js';
import * as llmApi from '../api/llm.js';
import * as promptsApi from '../api/prompts.js';
import FileBrowserModal from '../components/settings/FileBrowserModal.vue';

const store = useSettingsStore();
const editing = ref(null);
const isNew = ref(false);
const showBrowser = ref(false);

// System prompts (bundled with app) — fetched once at mount
const promptsList = ref([]);
const systemPrompts = ref({});

function overrideKey(name) {
  // narrative → narrativePrompt, chub_import → chubImportPrompt
  const camel = name.split('_').map((p, i) => i === 0 ? p : p.charAt(0).toUpperCase() + p.slice(1)).join('');
  return `${camel}Prompt`;
}

function promptLabel(name) {
  const map = {
    narrative: 'Narrative Prompt',
    meta: 'Meta-Analysis Prompt',
    chub_import: 'Chub / Card Import Prompt',
  };
  return map[name] || name;
}

function isOverridden(name) {
  if (!editing.value) return false;
  const v = editing.value[overrideKey(name)];
  return typeof v === 'string';
}

function toggleOverride(name, on) {
  if (!editing.value) return;
  const key = overrideKey(name);
  if (on) {
    // Seed the override with the current system prompt so the user can edit from there
    editing.value[key] = systemPrompts.value[name] || '';
  } else {
    editing.value[key] = null;
  }
}

// LLM Engine state
const llmExePath = ref('');
const llmStatus = ref({ running: false, modelPath: null, port: null });
const llmLoading = ref(false);
const llmLoadingText = ref('');
const llmConfiguring = ref(false);
const llmError = ref('');
const llmVersionInfo = ref({ installed: null, latest: null, updateAvailable: false });
const llmVariant = ref('cuda13');
const llmDownloading = ref(false);

const providerStatus = ref({ "llama-server": true, "xai": false, "openai": false });

const isActivePreset = computed(() =>
  llmStatus.value.running
  && editing.value?.modelPath
  && llmStatus.value.modelPath === editing.value.modelPath,
);

function shortModelName(path) {
  if (!path) return '';
  return path.split(/[\\/]/).pop();
}

function onFileSelected(path) {
  if (editing.value) editing.value.modelPath = path;
  showBrowser.value = false;
}

onMounted(async () => {
  store.fetchPresets();
  try {
    const status = await llmApi.getLlmStatus();
    llmStatus.value = status;
    if (status.exePath) llmExePath.value = status.exePath;
  } catch { /* backend not running yet */ }
  try {
    providerStatus.value = await llmApi.getProviderStatus();
  } catch { /* ok */ }
  try {
    llmVersionInfo.value = await llmApi.getVersion();
  } catch { /* ok */ }
  try {
    promptsList.value = await promptsApi.listPrompts();
    // Fetch full bodies in parallel so the read-only textareas show real content
    const bodies = await Promise.all(promptsList.value.map(p => promptsApi.getPrompt(p.name)));
    for (const b of bodies) systemPrompts.value[b.name] = b.body;
  } catch { /* prompts API not yet available */ }
});

async function saveLlmExe() {
  llmConfiguring.value = true;
  llmError.value = '';
  try {
    await llmApi.configureExe(llmExePath.value);
  } catch {
    llmError.value = 'Invalid executable path';
  } finally {
    llmConfiguring.value = false;
  }
}

async function doLoad() {
  if (!editing.value?.modelPath) { llmError.value = 'Select a GGUF model first'; return; }
  llmLoading.value = true;
  llmLoadingText.value = 'Loading model...';
  llmError.value = '';
  try {
    const result = await llmApi.loadModel({
      modelPath: editing.value.modelPath,
      gpuLayers: editing.value.gpuLayers ?? 99,
      contextSize: editing.value.contextSize ?? 65536,
      port: editing.value.port ?? 8080,
    });
    llmStatus.value = { running: result.running, modelPath: result.modelPath, port: result.port };
  } catch (err) {
    llmError.value = err?.message || 'Failed to load model';
  } finally {
    llmLoading.value = false;
  }
}

async function doDownload() {
  llmDownloading.value = true;
  llmError.value = '';
  try {
    const result = await llmApi.downloadLlamaServer(llmVariant.value);
    llmVersionInfo.value = await llmApi.getVersion();
    llmExePath.value = result.exe;
  } catch (err) {
    llmError.value = err?.message || 'Download failed';
  } finally {
    llmDownloading.value = false;
  }
}

async function doUnload() {
  llmLoading.value = true;
  llmLoadingText.value = 'Unloading...';
  llmError.value = '';
  try {
    await llmApi.unloadModel();
    llmStatus.value = { running: false, modelPath: null, port: null };
  } catch (err) {
    llmError.value = err?.message || 'Failed to unload';
  } finally {
    llmLoading.value = false;
  }
}

function edit(preset) {
  editing.value = withDefaults(JSON.parse(JSON.stringify(preset)));
  isNew.value = false;
  refreshModels();
}

function duplicate(preset) {
  const copy = withDefaults(JSON.parse(JSON.stringify(preset)));
  copy.id = copy.id + '_copy';
  copy.name = copy.name + ' (copy)';
  editing.value = copy;
  isNew.value = true;
  refreshModels();
}

function startNew() {
  // Clone the "default" preset so samplers, token budget, and prompts are pre-filled.
  const base = store.presets.find(p => p.id === 'default');
  const template = base
    ? JSON.parse(JSON.stringify(base))
    : {
        temperature: 0.7, topP: 0.8, topK: 20, minP: null,
        presencePenalty: 1.5, frequencyPenalty: null, repeatPenalty: null, seed: null,
        maxTokens: 10240, contextSize: 65536,
        thinkingTokens: 1500, narrativeTokens: 500, suggestionTokens: 200,
        chunkUpdateInterval: 5,
        provider: 'llama-server',
        providerConfig: {
          xai: { model: 'grok-beta', baseUrl: 'https://api.x.ai/v1' },
          openai: { model: 'gpt-4o-mini', baseUrl: 'https://api.openai.com/v1' }
        }
      };
  template.id = '';
  template.name = '';
  template.modelPath = '';
  editing.value = withDefaults(template);
  isNew.value = true;
  refreshModels();
}

function withDefaults(p) {
  // Fill in fields that may be missing on legacy preset JSONs
  if (!p.provider) p.provider = 'llama-server';
  if (!p.providerConfig) p.providerConfig = {
    xai: { model: 'grok-beta', baseUrl: 'https://api.x.ai/v1' },
    openai: { model: 'gpt-4o-mini', baseUrl: 'https://api.openai.com/v1' }
  };
  if (p.modelPath == null) p.modelPath = '';
  if (p.gpuLayers == null) p.gpuLayers = 99;
  if (p.port == null) p.port = 8080;
  if (p.contextSize == null) p.contextSize = 65536;
  return p;
}

async function save() {
  if (!editing.value.id || !editing.value.name) return;
  const saved = await store.savePreset(editing.value);
  if (saved) {
    editing.value = withDefaults(JSON.parse(JSON.stringify(saved)));
    isNew.value = false;
  }
}

async function remove(id) {
  if (window.confirm('Delete this preset?')) {
    await store.deletePreset(id);
    if (editing.value?.id === id) editing.value = null;
  }
}

async function setAsDefault() {
  if (!editing.value) return;
  await store.makeDefault(editing.value.id);
  // Reflect on the currently edited copy as well
  editing.value.isDefault = true;
}
const remoteModels = ref([]);
const fetchingModels = ref(false);

async function refreshModels() {
  if (!editing.value || !['xai', 'openai'].includes(editing.value.provider)) {
    remoteModels.value = [];
    return;
  }
  const provider = editing.value.provider;
  const baseUrl = editing.value.providerConfig[provider].baseUrl;
  fetchingModels.value = true;
  try {
    const res = await llmApi.getProviderModels(provider, baseUrl);
    remoteModels.value = res.models || [];
  } catch (e) {
    console.error("Failed to fetch models", e);
    remoteModels.value = [];
  } finally {
    fetchingModels.value = false;
  }
}

watch(() => editing.value?.provider, refreshModels);

</script>
