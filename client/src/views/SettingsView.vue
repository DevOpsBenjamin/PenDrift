<template>
  <div class="flex-1 max-w-5xl mx-auto px-4 sm:px-6 py-6 sm:py-10 w-full">

    <!-- LLM Engine Panel -->
    <div class="mb-8 p-5 bg-bg-surface rounded-xl border border-border">
      <h2 class="font-body text-lg font-bold mb-4">LLM Engine</h2>

      <!-- llama-server version / download -->
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

      <!-- Manual exe path override -->
      <details class="mb-4">
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

      <!-- Model loading -->
      <div class="flex flex-col gap-1.5 mb-4">
        <label class="text-xs text-text-muted font-medium uppercase tracking-wider">GGUF Model Path</label>
        <input v-model="llmModelPath" placeholder="I:\models\qwen3.5-27b-q3.gguf"
          class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm font-mono
                 focus:outline-none focus:border-accent transition-colors" />
      </div>

      <div class="grid grid-cols-3 sm:grid-cols-4 gap-3 mb-4">
        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-text-muted">GPU Layers</label>
          <input v-model.number="llmGpuLayers" type="number" min="0" max="999"
            class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   focus:outline-none focus:border-accent transition-colors" />
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-text-muted">Context Size</label>
          <input v-model.number="llmContextSize" type="number" step="1024" min="1024"
            class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   focus:outline-none focus:border-accent transition-colors" />
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-text-muted">Port</label>
          <input v-model.number="llmPort" type="number" min="1024" max="65535"
            class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   focus:outline-none focus:border-accent transition-colors" />
        </div>
      </div>

      <div class="flex items-center gap-3">
        <button
          class="px-5 py-2.5 rounded-lg text-white text-sm font-semibold transition-all cursor-pointer active:scale-95"
          :class="llmStatus.running
            ? 'bg-error hover:bg-error/80'
            : 'bg-accent hover:bg-accent-hover'"
          :disabled="llmLoading || (!llmVersionInfo.installed && !llmExePath)"
          @click="llmStatus.running ? doUnload() : doLoad()"
        >
          <span v-if="llmLoading">{{ llmLoadingText }}</span>
          <span v-else-if="llmStatus.running">Unload Model</span>
          <span v-else>Load Model</span>
        </button>
        <div class="flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full" :class="llmStatus.running ? 'bg-green-400' : 'bg-text-muted/30'"></span>
          <span class="text-sm text-text-secondary">
            <template v-if="llmStatus.running">
              Loaded — port {{ llmStatus.port }}
            </template>
            <template v-else>No model loaded</template>
          </span>
        </div>
        <span v-if="llmError" class="text-sm text-error">{{ llmError }}</span>
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
          <span class="truncate">{{ preset.name }}</span>
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

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Provider</label>
            <select v-model="editing.provider"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors">
              <option value="ollama">Ollama</option>
              <option value="lmstudio">LM Studio</option>
              <option value="koboldcpp">KoboldCpp</option>
              <option value="generic">Generic (OpenAI-compatible)</option>
            </select>
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">API Endpoint</label>
            <input v-model="editing.apiEndpoint" :placeholder="endpointPlaceholder"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors" />
          </div>
        </div>

        <div class="flex items-end gap-3">
          <button
            class="px-4 py-2 text-xs bg-bg-surface border border-border rounded-lg text-text-secondary
                   hover:text-text-primary hover:border-accent/40 transition-all cursor-pointer whitespace-nowrap"
            :class="{ 'opacity-50 cursor-wait': loadingModels }"
            :disabled="loadingModels"
            @click="refreshModels"
          >{{ loadingModels ? 'Loading...' : 'Refresh Models' }}</button>
          <span v-if="availableModels.length" class="text-xs text-text-muted">
            {{ availableModels.length }} model(s) found
          </span>
          <span v-else-if="!loadingModels" class="text-xs text-text-muted">
            No models found — check endpoint and provider
          </span>
        </div>

        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Narrative Model</label>
          <ModelSelect v-model="editing.narrativeModel" :models="availableModels" placeholder="Select narrative model..." />
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Meta-Analysis Model</label>
            <ModelSelect v-model="editing.metaModel" :models="availableModels" placeholder="Same as narrative if empty" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Utility Model (JSON fixer)</label>
            <ModelSelect v-model="editing.utilityModel" :models="availableModels" placeholder="Same as narrative if empty" />
          </div>
        </div>

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

        <h3 class="text-xs text-text-muted font-semibold uppercase tracking-wider pt-3 border-t border-border-subtle">Token Budget</h3>
        <div class="grid grid-cols-3 sm:grid-cols-5 gap-3">
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted">Thinking</label>
            <input v-model.number="editing.thinkingTokens" type="number" step="100" min="0"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted">Narrative</label>
            <input v-model.number="editing.narrativeTokens" type="number" step="100" min="100"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted">Suggestions</label>
            <input v-model.number="editing.suggestionTokens" type="number" step="50" min="0"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted">Max Tokens (meta)</label>
            <input v-model.number="editing.maxTokens" type="number" step="256" min="256"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted">Context Size</label>
            <input v-model.number="editing.contextSize" type="number" step="1024" min="1024"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
        </div>
        <p class="text-xs text-text-muted -mt-2">
          Total generation budget: {{ (editing.thinkingTokens || 0) + (editing.narrativeTokens || 0) + (editing.suggestionTokens || 0) }} tokens
        </p>

        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Update Interval</label>
            <input v-model.number="editing.chunkUpdateInterval" type="number" min="1"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Recent Chunks</label>
            <input v-model.number="editing.recentChunksCount" type="number" min="1"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Think Start</label>
            <input v-model="editing.thinkBlockStart"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm font-mono
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Think End</label>
            <input v-model="editing.thinkBlockEnd"
              class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm font-mono
                     focus:outline-none focus:border-accent transition-colors" />
          </div>
        </div>

        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Narrative Prompt</label>
          <textarea v-model="editing.narrativePrompt" rows="6"
            class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   font-ui resize-y min-h-32 focus:outline-none focus:border-accent transition-colors"></textarea>
        </div>

        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Meta-Analysis Prompt</label>
          <textarea v-model="editing.metaPrompt" rows="6"
            class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   font-ui resize-y min-h-32 focus:outline-none focus:border-accent transition-colors"></textarea>
        </div>

        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Chub/Card Import Prompt</label>
          <textarea v-model="editing.chubImportPrompt" rows="6"
            class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   font-ui resize-y min-h-32 focus:outline-none focus:border-accent transition-colors"
            placeholder="System prompt for converting character cards to PenDrift templates..."></textarea>
        </div>

        <div class="flex justify-between pt-2">
          <button
            v-if="!isNew && editing.id !== 'default'"
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
        Select a preset to edit or create a new one.
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { useSettingsStore } from '../stores/settings.js';
import * as presetsApi from '../api/presets.js';
import * as llmApi from '../api/llm.js';
import ModelSelect from '../components/presets/ModelSelect.vue';

const store = useSettingsStore();
const editing = ref(null);
const isNew = ref(false);
const availableModels = ref([]);
const loadingModels = ref(false);

// LLM Engine state
const llmExePath = ref('');
const llmModelPath = ref('');
const llmGpuLayers = ref(99);
const llmContextSize = ref(65536);
const llmPort = ref(8080);
const llmStatus = ref({ running: false, modelPath: null, port: null });
const llmLoading = ref(false);
const llmLoadingText = ref('');
const llmConfiguring = ref(false);
const llmError = ref('');
const llmVersionInfo = ref({ installed: null, latest: null, updateAvailable: false });
const llmVariant = ref('cuda13');
const llmDownloading = ref(false);

const endpointPlaceholder = computed(() => {
  const p = editing.value?.provider;
  if (p === 'ollama') return 'http://localhost:11434/v1/chat/completions';
  if (p === 'lmstudio') return 'http://localhost:1234/v1/chat/completions';
  if (p === 'koboldcpp') return 'http://localhost:5001/v1/chat/completions';
  return 'http://localhost:8080/v1/chat/completions';
});

onMounted(async () => {
  store.fetchPresets();
  try {
    const status = await llmApi.getLlmStatus();
    llmStatus.value = status;
    if (status.modelPath) llmModelPath.value = status.modelPath;
    if (status.exePath) llmExePath.value = status.exePath;
  } catch { /* backend not running yet */ }
  try {
    llmVersionInfo.value = await llmApi.getVersion();
  } catch { /* ok */ }
});

async function saveLlmExe() {
  llmConfiguring.value = true;
  llmError.value = '';
  try {
    await llmApi.configureExe(llmExePath.value);
  } catch (err) {
    llmError.value = 'Invalid executable path';
  } finally {
    llmConfiguring.value = false;
  }
}

async function doLoad() {
  if (!llmModelPath.value) { llmError.value = 'Select a GGUF model first'; return; }
  llmLoading.value = true;
  llmLoadingText.value = 'Loading model...';
  llmError.value = '';
  try {
    const result = await llmApi.loadModel({
      modelPath: llmModelPath.value,
      gpuLayers: llmGpuLayers.value,
      contextSize: llmContextSize.value,
      port: llmPort.value,
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

async function refreshModels() {
  if (!editing.value?.apiEndpoint) return;
  loadingModels.value = true;
  try {
    availableModels.value = await presetsApi.listModels(
      editing.value.apiEndpoint,
      editing.value.provider || 'generic',
    );
  } catch {
    availableModels.value = [];
  } finally {
    loadingModels.value = false;
  }
}

function edit(preset) {
  editing.value = JSON.parse(JSON.stringify(preset));
  isNew.value = false;
  availableModels.value = [];
}

function duplicate(preset) {
  const copy = JSON.parse(JSON.stringify(preset));
  copy.id = copy.id + '_copy';
  copy.name = copy.name + ' (copy)';
  editing.value = copy;
  isNew.value = true;
  availableModels.value = [];
}

function startNew() {
  isNew.value = true;
  editing.value = {
    id: '',
    name: '',
    provider: 'ollama',
    apiEndpoint: 'http://localhost:11434/v1/chat/completions',
    narrativeModel: '',
    metaModel: '',
    utilityModel: '',
    temperature: 0.7,
    topP: 0.8,
    topK: 20,
    minP: null,
    presencePenalty: 1.5,
    frequencyPenalty: null,
    repeatPenalty: null,
    seed: null,
    maxTokens: 10240,
    contextSize: 65536,
    thinkingTokens: 1500,
    narrativeTokens: 500,
    suggestionTokens: 200,
    recentChunksCount: 20,
    chunkUpdateInterval: 5,
    thinkBlockStart: '<think>',
    thinkBlockEnd: '</think>',
    narrativePrompt: '',
    metaPrompt: '',
    formatFixerPrompt: '',
    chubImportPrompt: '',
  };
}

async function save() {
  if (!editing.value.id || !editing.value.name) return;
  const saved = await store.savePreset(editing.value);
  if (saved) {
    editing.value = JSON.parse(JSON.stringify(saved));
    isNew.value = false;
  }
}

async function remove(id) {
  if (window.confirm('Delete this preset?')) {
    await store.deletePreset(id);
    if (editing.value?.id === id) editing.value = null;
  }
}
</script>
