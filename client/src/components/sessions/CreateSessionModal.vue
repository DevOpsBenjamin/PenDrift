<template>
  <Teleport to="body">
    <div class="fixed inset-0 bg-bg-overlay backdrop-blur-sm flex items-center justify-center z-50 p-4" @click.self="$emit('close')">
      <div class="bg-bg-secondary border border-border rounded-2xl w-full max-w-6xl flex flex-col shadow-2xl max-h-[92vh]">
        <!-- Header -->
        <div class="flex items-center justify-between px-6 py-4 border-b border-border">
          <div>
            <h2 class="text-lg font-semibold text-text-primary">New Session</h2>
            <p class="text-xs text-text-muted mt-0.5">Pick a template to begin.</p>
          </div>
          <button class="text-text-muted hover:text-text-primary cursor-pointer transition-colors" @click="$emit('close')">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <!-- Search -->
        <div class="px-6 py-3 border-b border-border-subtle">
          <input
            v-model="search"
            placeholder="Search templates by name…"
            class="w-full px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   focus:outline-none focus:border-accent transition-colors"
          />
        </div>

        <!-- Template grid -->
        <div class="flex-1 overflow-y-auto px-6 py-4">
          <div v-if="!filteredTemplates.length" class="text-center text-text-muted italic py-12">
            <template v-if="search">No template matches "{{ search }}".</template>
            <template v-else>No templates yet — import one from the Templates page.</template>
          </div>
          <div v-else class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            <button
              v-for="tpl in filteredTemplates"
              :key="tpl.id"
              type="button"
              class="group relative flex flex-col text-left bg-bg-surface rounded-xl overflow-hidden border-2 transition-all cursor-pointer hover:scale-[1.02]"
              :class="selectedTemplate === tpl.id
                ? 'border-accent shadow-lg shadow-accent/20'
                : 'border-border-subtle hover:border-border'"
              @click="selectedTemplate = tpl.id"
            >
              <!-- Cover image (or placeholder) -->
              <div class="aspect-[4/5] bg-bg-primary relative overflow-hidden">
                <img
                  v-if="tpl.coverImage"
                  :src="imgUrl(tpl)"
                  class="absolute inset-0 w-full h-full object-cover"
                />
                <div v-else class="absolute inset-0 flex items-center justify-center text-text-muted">
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-12 h-12 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                </div>
                <!-- Selection check -->
                <div v-if="selectedTemplate === tpl.id"
                  class="absolute top-2 right-2 w-7 h-7 bg-accent rounded-full flex items-center justify-center text-white shadow-lg">
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                </div>
              </div>
              <!-- Card body -->
              <div class="px-3 py-2.5 flex flex-col gap-1 flex-1">
                <h3 class="text-sm font-semibold text-text-primary line-clamp-2">{{ tpl.name }}</h3>
                <p v-if="tpl.description" class="text-xs text-text-muted line-clamp-3">{{ tpl.description }}</p>
                <div class="flex gap-2 mt-auto pt-1 text-[10px] text-text-muted">
                  <span v-if="tpl.characters?.length">{{ tpl.characters.length }} char</span>
                  <span v-if="tpl.maskedIntents?.length">·</span>
                  <span v-if="tpl.maskedIntents?.length">{{ tpl.maskedIntents.length }} intents</span>
                </div>
              </div>
            </button>
          </div>
        </div>

        <!-- Bottom: title + preset + create -->
        <div class="px-6 py-4 border-t border-border bg-bg-surface/30">
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
            <div class="flex flex-col gap-1.5">
              <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Title (optional)</label>
              <input
                v-model="title"
                :placeholder="placeholderTitle"
                class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                       placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors"
              />
            </div>
            <div class="flex flex-col gap-1.5">
              <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Settings Preset</label>
              <select
                v-model="selectedPreset"
                class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                       focus:outline-none focus:border-accent transition-colors"
              >
                <option v-for="p in settingsStore.presets" :key="p.id" :value="p.id">{{ p.name }}</option>
              </select>
            </div>
          </div>
          <div class="flex justify-end gap-3">
            <button
              class="px-4 py-2 border border-border rounded-lg text-text-secondary text-sm cursor-pointer
                     hover:bg-bg-surface hover:text-text-primary transition-all"
              @click="$emit('close')"
            >Cancel</button>
            <button
              class="px-5 py-2 bg-accent rounded-lg text-white text-sm font-semibold cursor-pointer
                     hover:bg-accent-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              :disabled="!selectedTemplate"
              @click="create"
            >Create Session</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { useSettingsStore } from '../../stores/settings.js';
import * as templatesApi from '../../api/templates.js';

const props = defineProps({ templates: Array });
const emit = defineEmits(['close', 'create']);

const settingsStore = useSettingsStore();
const selectedTemplate = ref('');
const selectedPreset = ref('default');
const title = ref('');
const search = ref('');

const filteredTemplates = computed(() => {
  const q = search.value.trim().toLowerCase();
  if (!q) return props.templates;
  return props.templates.filter(t =>
    (t.name || '').toLowerCase().includes(q) ||
    (t.description || '').toLowerCase().includes(q),
  );
});

const placeholderTitle = computed(() => {
  if (!selectedTemplate.value) return 'Select a template to set default title';
  const t = props.templates.find(x => x.id === selectedTemplate.value);
  return t ? t.name : '';
});

function imgUrl(template) {
  return templatesApi.templateImageUrl(template);
}

onMounted(() => {
  if (!settingsStore.presets.length) settingsStore.fetchPresets();
});

function create() {
  if (!selectedTemplate.value) return;
  emit('create', {
    templateId: selectedTemplate.value,
    settingsPresetId: selectedPreset.value,
    title: title.value || undefined,
  });
}
</script>
