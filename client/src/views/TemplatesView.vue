<template>
  <div class="flex-1 max-w-5xl mx-auto px-4 sm:px-6 py-6 sm:py-10 w-full">
    <div class="flex items-center justify-between mb-6 sm:mb-8 gap-3">
      <h1 class="font-body text-2xl sm:text-3xl font-bold">Templates</h1>
      <div class="flex gap-2">
        <button
          class="px-4 py-2.5 border border-border rounded-lg text-text-secondary text-sm font-semibold cursor-pointer
                 hover:border-accent/40 hover:text-text-primary transition-all active:scale-95 flex items-center gap-2"
          @click="showImport = true"
          title="Import a character card from chub.ai or a JSON file"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Import Card
        </button>
        <button
          class="px-4 py-2.5 bg-accent rounded-lg text-white text-sm font-semibold cursor-pointer
                 hover:bg-accent-hover transition-colors active:scale-95"
          @click="startNew"
        >+ New Template</button>
      </div>
    </div>

    <ImportChubModal
      v-if="showImport"
      @close="showImport = false"
      @queued="onImportQueued"
    />

    <div class="flex flex-col md:flex-row gap-6">
      <!-- Template list -->
      <aside class="md:w-60 md:min-w-60 flex md:flex-col gap-2 overflow-x-auto md:overflow-x-visible pb-2 md:pb-0">
        <div
          v-for="tpl in store.templates"
          :key="tpl.id"
          class="group flex items-center gap-2 px-2 py-2 rounded-lg cursor-pointer text-sm whitespace-nowrap
                 transition-all duration-150"
          :class="editing?.id === tpl.id
            ? 'bg-bg-surface text-text-primary font-medium'
            : 'text-text-secondary hover:bg-bg-surface/50'"
          @click="edit(tpl)"
        >
          <div class="w-9 h-9 rounded shrink-0 bg-bg-primary border border-border-subtle overflow-hidden flex items-center justify-center">
            <img v-if="tpl.coverImage" :src="imgUrl(tpl)" class="w-full h-full object-cover" />
            <span v-else class="text-[10px] text-text-muted">—</span>
          </div>
          <span class="truncate flex-1 min-w-0">{{ tpl.name }}</span>
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
      <div v-if="editing" class="flex-1 flex flex-col gap-4">
        <!-- Action bar -->
        <div class="flex justify-between items-center gap-3 pb-3 border-b border-border-subtle">
          <div class="flex gap-2">
            <button
              v-if="!isNew"
              class="px-4 py-2 border border-error/30 rounded-lg text-error text-sm
                     hover:bg-error/10 transition-all cursor-pointer"
              @click="remove(editing.id)"
            >Delete</button>
            <button
              v-if="!isNew"
              class="px-3 py-2 border border-border rounded-lg text-text-muted text-sm
                     hover:bg-bg-surface hover:text-text-primary transition-all cursor-pointer"
              @click="openHistory"
              title="View past versions of this template"
            >History</button>
            <button
              v-if="!isNew"
              class="px-3 py-2 border border-border rounded-lg text-text-muted text-sm
                     hover:bg-bg-surface hover:text-text-primary transition-all cursor-pointer
                     disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent"
              :disabled="!editing.thinking"
              :title="editing.thinking ? 'View what the model understood when this version was generated' : 'No thinking on this version (manual edit or restore)'"
              @click="showThinking = true"
            ></button>
          </div>
          <div class="flex gap-3">
            <button
              class="px-4 py-2 border border-border rounded-lg text-text-secondary text-sm
                     hover:bg-bg-surface hover:text-text-primary transition-all cursor-pointer"
              @click="editing = null"
            >Cancel</button>
            <button
              class="px-5 py-2 bg-accent rounded-lg text-white text-sm font-semibold
                     hover:bg-accent-hover transition-colors cursor-pointer active:scale-95
                     disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-accent"
              :disabled="!isDirty"
              :title="isDirty ? 'Save changes' : 'No changes to save'"
              @click="save"
            >Save</button>
          </div>
        </div>

        <!-- Cover image + upload -->
        <div class="flex items-start gap-4">
          <div class="w-28 h-28 rounded-lg shrink-0 bg-bg-primary border border-border overflow-hidden flex items-center justify-center">
            <img v-if="editing.coverImage" :src="imgUrl(editing)" class="w-full h-full object-cover" />
            <span v-else class="text-xs text-text-muted">No image</span>
          </div>
          <div class="flex flex-col gap-2 flex-1">
            <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Cover Image</label>
            <input ref="imageInput" type="file" accept="image/*" class="hidden" @change="onImageChosen" />
            <div class="flex gap-2">
              <button
                class="px-3 py-1.5 bg-bg-primary border border-border rounded-lg text-text-secondary text-sm
                       hover:border-accent/40 hover:text-text-primary transition-all cursor-pointer disabled:opacity-50"
                :disabled="isNew || imageUploading"
                @click="imageInput?.click()"
                :title="isNew ? 'Save the template first to be able to upload an image' : 'Upload or replace cover image'"
              >{{ imageUploading ? 'Uploading…' : (editing.coverImage ? 'Replace…' : 'Upload…') }}</button>
              <button
                v-if="editing.coverImage"
                class="px-3 py-1.5 border border-border rounded-lg text-text-muted text-sm
                       hover:border-error/40 hover:text-error transition-all cursor-pointer disabled:opacity-50"
                :disabled="imageUploading"
                @click="removeImage"
              >Remove</button>
            </div>
            <p class="text-xs text-text-muted">PNG, JPG, WebP, GIF. Helps you spot the template at a glance.</p>
          </div>
        </div>

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
          <textarea v-model="editing.description" rows="3"
            class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   resize-y focus:outline-none focus:border-accent transition-colors"></textarea>
        </div>

        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Scenario</label>
          <textarea v-model="editing.scenario" rows="6"
            class="px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                   resize-y focus:outline-none focus:border-accent transition-colors"></textarea>
        </div>

        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-text-muted font-medium uppercase tracking-wider">Style Instructions</label>
          <textarea v-model="editing.systemPromptAdditions" rows="5"
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
              <textarea v-model="char.description" rows="6"
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

        <!-- Milestones section -->
        <div class="pt-4 border-t border-border-subtle">
          <div class="flex items-center gap-3 mb-1">
            <h3 class="text-sm font-semibold">Milestones</h3>
            <button
              class="text-xs px-2.5 py-1 border border-dashed border-border rounded-md text-text-muted
                     hover:border-accent/40 hover:text-accent transition-all cursor-pointer"
              @click="editing.milestones.push('')"
            >+ Add</button>
          </div>
          <p class="text-xs text-text-muted mb-3">Narrative waypoints — key moments the story can progress through. The director can request a jump to any of them via directive.</p>

          <div
            v-for="(_, i) in editing.milestones"
            :key="i"
            class="flex gap-2 items-start mb-2"
          >
            <span class="text-xs text-text-muted/60 mt-2.5 shrink-0 w-6 text-right">{{ i + 1 }}.</span>
            <textarea v-model="editing.milestones[i]" rows="4"
              class="flex-1 px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
                     resize-y focus:outline-none focus:border-accent transition-colors"
              placeholder="e.g. 'Wedding day: alone with the bride in the bridal suite, hours before the ceremony.'"></textarea>
            <button
              class="text-text-muted hover:text-accent transition-colors p-1 mt-1.5"
              @click="editing.milestones.splice(i, 1)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <!-- Sources section (only for existing templates) -->
        <div v-if="!isNew" class="pt-4 border-t border-border-subtle">
          <div class="flex items-center gap-3 mb-1">
            <h3 class="text-sm font-semibold">Sources</h3>
            <input ref="sourceFileInput" type="file" accept="application/json,.json" class="hidden" @change="onSourceFileChosen" />
            <button
              class="text-xs px-2.5 py-1 border border-dashed border-border rounded-md text-text-muted
                     hover:border-accent/40 hover:text-accent transition-all cursor-pointer"
              :disabled="sourcesBusy"
              @click="sourceFileInput?.click()"
              title="Attach a chub.ai card JSON to this template"
            >+ Attach JSON</button>
          </div>
          <p class="text-xs text-text-muted mb-3">
            Original character cards attached to this template. Use "Rerun" on a source to re-analyze it with the current import prompt — useful for catching info that earlier prompts missed.
          </p>
          <div v-if="!sourcesList.length" class="text-xs text-text-muted italic">
            No sources attached. Attach the original chub card JSON to enable Rerun.
          </div>
          <div v-else class="flex flex-col gap-2">
            <div v-for="src in sourcesList" :key="src.filename"
              class="flex items-center gap-3 px-3 py-2 bg-bg-primary border border-border-subtle rounded-lg">
              <div class="flex-1 min-w-0">
                <div class="font-mono text-xs text-text-secondary truncate">{{ src.filename }}</div>
                <a v-if="src.url" :href="src.url" target="_blank" rel="noopener"
                  class="text-[11px] text-accent/70 hover:underline truncate block">{{ src.url }}</a>
              </div>
              <span class="text-xs text-text-muted shrink-0">{{ formatSize(src.sizeBytes) }} · {{ formatDate(src.addedAt) }}</span>
              <button
                class="px-2.5 py-1 text-xs border border-border rounded text-text-secondary
                       hover:border-accent/40 hover:text-accent transition-all cursor-pointer disabled:opacity-50"
                :disabled="llmBusy"
                @click="runRerun(src.filename)"
                :title="'Audit & correct the template using THIS source (same character)'"
              >{{ rerunning && rerunSource === src.filename ? llmStatusLabel('Rerun') : 'Rerun' }}</button>
              <button
                class="px-2.5 py-1 text-xs border border-border rounded text-text-secondary
                       hover:border-accent/40 hover:text-accent transition-all cursor-pointer disabled:opacity-50"
                :disabled="llmBusy"
                @click="runEnrich(src.filename)"
                :title="'Merge THIS card into the template (different character, same universe)'"
              >{{ enriching && enrichSource === src.filename ? llmStatusLabel('Enrich') : 'Enrich' }}</button>
              <button
                class="text-text-muted hover:text-error transition-colors p-1"
                @click="deleteSource(src.filename)"
                title="Detach this source"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
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
            <textarea v-model="editing.maskedIntents[i]" rows="4"
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

      </div>

      <div v-else class="flex-1 flex items-center justify-center text-text-muted italic text-sm py-20">
        Select a template to edit or create a new one.
      </div>
    </div>

    <!-- History modal -->
    <Teleport to="body">
      <div v-if="showHistory" class="fixed inset-0 bg-bg-overlay backdrop-blur-sm flex items-center justify-center z-50 p-4" @click.self="showHistory = false">
        <div class="bg-bg-secondary border border-border rounded-2xl w-full max-w-2xl flex flex-col shadow-2xl max-h-[80vh]">
          <div class="px-5 py-4 border-b border-border flex items-center justify-between">
            <h2 class="text-lg font-semibold">Version History — {{ editing?.name }}</h2>
            <button class="text-text-muted hover:text-text-primary cursor-pointer" @click="showHistory = false">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div class="flex-1 overflow-y-auto px-5 py-4">
            <div v-if="!historyEntries.length" class="text-center text-text-muted italic py-8">
              No versions recorded.
            </div>
            <ul v-else class="space-y-2">
              <li v-for="entry in reversedHistory" :key="entry.version"
                class="rounded-lg bg-bg-primary border border-border-subtle">
                <div class="flex items-center gap-3 p-3">
                  <span class="font-mono text-xs text-accent shrink-0 w-12">{{ entry.version }}</span>
                  <div class="flex-1 min-w-0">
                    <div class="text-sm text-text-primary">{{ entry.action }}</div>
                    <div class="text-xs text-text-muted truncate">
                      <template v-if="entry.at">{{ formatDate(entry.at) }}</template>
                      <span v-if="entry.url" class="ml-2">· <a :href="entry.url" target="_blank" class="text-accent/70 hover:underline">source</a></span>
                    </div>
                  </div>
                  <button
                    v-if="priorVersion(entry.version)"
                    class="px-2.5 py-1 text-xs border border-border rounded text-text-secondary
                           hover:border-accent/40 hover:text-accent transition-all cursor-pointer disabled:opacity-50"
                    :disabled="diffLoading[entry.version]"
                    @click="toggleDiff(entry.version)"
                    :title="`Compare against ${priorVersion(entry.version)}`"
                  >{{ expandedDiffs[entry.version] ? 'Hide' : (diffLoading[entry.version] ? 'Loading…' : `Diff vs ${priorVersion(entry.version)}`) }}</button>
                  <button
                    class="px-3 py-1 text-xs border border-border rounded text-text-secondary
                           hover:border-accent/40 hover:text-text-primary transition-all cursor-pointer"
                    :disabled="restoring"
                    @click="restoreVersion(entry.version)"
                  >Restore</button>
                </div>
                <div v-if="expandedDiffs[entry.version]" class="border-t border-border-subtle p-3 font-mono text-xs">
                  <div v-if="!diffCache[entry.version]?.length" class="text-text-muted italic">No differences from {{ priorVersion(entry.version) }}.</div>
                  <div v-else class="bg-bg-surface rounded overflow-x-auto">
                    <div
                      v-for="(row, i) in diffCache[entry.version]"
                      :key="i"
                      class="px-3 py-0.5 whitespace-pre-wrap"
                      :class="diffRowClass(row.kind)"
                    ><span class="select-none mr-2 opacity-60">{{ diffPrefix(row.kind) }}</span>{{ row.text }}</div>
                  </div>
                </div>
              </li>
            </ul>
          </div>
          <div class="px-5 py-3 border-t border-border flex justify-between">
            <button
              class="px-4 py-2 border border-border rounded-lg text-text-secondary text-sm
                     hover:bg-bg-surface hover:text-text-primary transition-all cursor-pointer"
              :disabled="checkpointing"
              @click="checkpoint"
            >{{ checkpointing ? 'Saving…' : 'Checkpoint current state' }}</button>
            <button
              class="px-4 py-2 border border-border rounded-lg text-text-secondary text-sm
                     hover:bg-bg-surface hover:text-text-primary transition-all cursor-pointer"
              @click="showHistory = false"
            >Close</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Thinking modal -->
    <Teleport to="body">
      <div v-if="showThinking" class="fixed inset-0 bg-bg-overlay backdrop-blur-sm flex items-center justify-center z-50 p-4" @click.self="showThinking = false">
        <div class="bg-bg-secondary border border-border rounded-2xl w-full max-w-3xl flex flex-col shadow-2xl max-h-[80vh]">
          <div class="px-5 py-4 border-b border-border flex items-center justify-between">
            <h2 class="text-lg font-semibold">Model Thinking — {{ editing?.name }}</h2>
            <button class="text-text-muted hover:text-text-primary cursor-pointer" @click="showThinking = false">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div class="flex-1 overflow-y-auto px-5 py-4">
            <p class="text-xs text-text-muted mb-3">
              What the model understood and decided when this version was generated. Captured at chub-import / enrich / rerun time. Cleared on restore.
            </p>
            <pre class="whitespace-pre-wrap font-mono text-xs text-text-primary bg-bg-primary border border-border-subtle rounded-lg p-4 leading-relaxed">{{ editing?.thinking || '(no thinking on this version)' }}</pre>
          </div>
          <div class="px-5 py-3 border-t border-border flex justify-end">
            <button
              class="px-4 py-2 border border-border rounded-lg text-text-secondary text-sm
                     hover:bg-bg-surface hover:text-text-primary transition-all cursor-pointer"
              @click="showThinking = false"
            >Close</button>
          </div>
        </div>
      </div>
    </Teleport>

  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue';
import { useSettingsStore } from '../stores/settings.js';
import { useJobsStore } from '../stores/jobs.js';
import * as templatesApi from '../api/templates.js';
import ImportChubModal from '../components/templates/ImportChubModal.vue';

const store = useSettingsStore();
const jobs = useJobsStore();
const editing = ref(null);
const editingPristine = ref(null);
const isNew = ref(false);

const isDirty = computed(() => {
  if (!editing.value) return false;
  if (isNew.value) return true;
  return JSON.stringify(editing.value) !== editingPristine.value;
});
const showImport = ref(false);
const imageInput = ref(null);
const imageUploading = ref(false);
const showHistory = ref(false);
const showThinking = ref(false);
const historyEntries = ref([]);
const restoring = ref(false);
const checkpointing = ref(false);
const expandedDiffs = ref({});
const diffLoading = ref({});
const diffCache = ref({});

const reversedHistory = computed(() => [...historyEntries.value].reverse());

function priorVersion(version) {
  // Sort versions ascending and return the one immediately before `version`
  const sorted = historyEntries.value.map(e => e.version).sort();
  const idx = sorted.indexOf(version);
  return idx > 0 ? sorted[idx - 1] : null;
}

async function toggleDiff(version) {
  if (expandedDiffs.value[version]) {
    expandedDiffs.value[version] = false;
    return;
  }
  const prior = priorVersion(version);
  if (!prior) return;
  if (!diffCache.value[version]) {
    diffLoading.value[version] = true;
    try {
      const res = await templatesApi.diffTemplateVersions(editing.value.id, prior, version);
      diffCache.value[version] = res.diff || [];
    } catch (err) {
      window.alert('Could not load diff: ' + (err.message || err));
      diffLoading.value[version] = false;
      return;
    }
    diffLoading.value[version] = false;
  }
  expandedDiffs.value[version] = true;
}

// Sources + Rerun + Enrich
const sourceFileInput = ref(null);
const sourcesList = ref([]);
const sourcesBusy = ref(false);
const rerunning = ref(false);
const rerunSource = ref(null);
const enriching = ref(false);
const enrichSource = ref(null);
const llmBusy = computed(() => rerunning.value || enriching.value);

// Live progress (model load / token rate / elapsed) lives in the JobsToastBar
// which subscribes to /api/jobs/stream globally. The button label here just
// shows "Rerun…" / "Enrich…" until the matching job in the store completes.
function llmStatusLabel(verb) {
  return `${verb}…`;
}

function diffRowClass(kind) {
  switch (kind) {
    case 'add': return 'bg-green-500/10 text-green-300';
    case 'remove': return 'bg-red-500/10 text-red-300';
    case 'hunk': return 'bg-bg-surface text-text-muted';
    default: return 'text-text-secondary';
  }
}

function diffPrefix(kind) {
  switch (kind) {
    case 'add': return '+';
    case 'remove': return '−';
    case 'hunk': return '@';
    default: return ' ';
  }
}

async function loadSources() {
  if (!editing.value || isNew.value) {
    sourcesList.value = [];
    return;
  }
  try {
    sourcesList.value = await templatesApi.listTemplateSources(editing.value.id);
  } catch {
    sourcesList.value = [];
  }
}

async function onSourceFileChosen(event) {
  const file = event.target.files?.[0];
  if (!file || !editing.value) return;
  sourcesBusy.value = true;
  try {
    const text = await file.text();
    let card;
    try {
      card = JSON.parse(text);
    } catch (e) {
      window.alert('Invalid JSON: ' + e.message);
      return;
    }
    const res = await templatesApi.attachTemplateSource(editing.value.id, card);
    await loadSources();
    if (res.coverAdded && res.coverImage) {
      editing.value.coverImage = res.coverImage;
      const idx = store.templates.findIndex(t => t.id === editing.value.id);
      if (idx >= 0) store.templates[idx].coverImage = res.coverImage;
    }
  } catch (err) {
    window.alert('Could not attach source: ' + (err.message || err));
  } finally {
    sourcesBusy.value = false;
    if (sourceFileInput.value) sourceFileInput.value.value = '';
  }
}

async function deleteSource(filename) {
  if (!editing.value) return;
  if (!window.confirm(`Detach source ${filename}? The card JSON will be deleted from disk.`)) return;
  try {
    await templatesApi.deleteTemplateSource(editing.value.id, filename);
    await loadSources();
  } catch (err) {
    window.alert('Could not delete source: ' + (err.message || err));
  }
}

// Track the rerun/enrich jobs we kicked off here so we can:
//  - clear the local "busy" UI state when they finish
//  - refresh the editor with the new version if the user is still on it
// Plain Map (not a Vue ref) because it's accessed only inside the watch
// handler — no reactivity needed and avoids any subtle proxy-vs-mutation gotcha.
const templateOpContexts = new Map();   // jobId → {busyRef, sourceRef, label, templateId}
const seenTerminalTemplateOps = new Set();  // jobIds we've already processed

async function _runLlmOnSource(apiCall, filename, busyRef, sourceRef, label) {
  if (!editing.value || llmBusy.value) return;
  busyRef.value = true;
  sourceRef.value = filename;
  try {
    const presetId = store.defaultPresetId();
    const res = await apiCall(editing.value.id, filename, presetId);
    if (!res?.jobId) {
      throw new Error('Backend did not return a jobId');
    }
    templateOpContexts.set(res.jobId, {
      busyRef, sourceRef, label, templateId: editing.value.id,
    });
  } catch (err) {
    window.alert(`${label} failed: ` + (err.message || err));
    busyRef.value = false;
    sourceRef.value = null;
  }
}

watch(() => jobs.jobs, async (current) => {
  for (const j of current) {
    if (!templateOpContexts.has(j.id)) continue;
    if (seenTerminalTemplateOps.has(j.id)) continue;
    if (j.status !== 'done' && j.status !== 'cancelled' && j.status !== 'error') continue;

    seenTerminalTemplateOps.add(j.id);
    const ctx = templateOpContexts.get(j.id);
    templateOpContexts.delete(j.id);
    if (ctx) {
      ctx.busyRef.value = false;
      ctx.sourceRef.value = null;
    }

    if (j.status === 'error') {
      window.alert(`${ctx?.label || 'Template op'} failed: ${j.error || 'unknown'}`);
      continue;
    }
    if (j.status !== 'done') continue;

    // Refresh the editor with the new version if the user is still on this
    // template. App.vue handles the sidebar refresh globally.
    if (editing.value && ctx && editing.value.id === ctx.templateId) {
      try {
        const tpl = await templatesApi.getTemplate(ctx.templateId);
        if (tpl) {
          editing.value = ensureFields(JSON.parse(JSON.stringify(tpl)));
          editingPristine.value = JSON.stringify(editing.value);
          historyEntries.value = await templatesApi.listTemplateVersions(ctx.templateId);
        }
      } catch { /* sidebar refresh still happens via App.vue */ }
    }
  }
}, { deep: true });

const runRerun = (filename) =>
  _runLlmOnSource(templatesApi.rerunTemplateAnalysis, filename, rerunning, rerunSource, 'Rerun');

const runEnrich = (filename) =>
  _runLlmOnSource(templatesApi.enrichTemplate, filename, enriching, enrichSource, 'Enrich');

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

async function openHistory() {
  if (!editing.value) return;
  showHistory.value = true;
  try {
    historyEntries.value = await templatesApi.listTemplateVersions(editing.value.id);
  } catch (err) {
    historyEntries.value = [];
    window.alert('Could not load history: ' + (err.message || err));
  }
}

async function checkpoint() {
  if (!editing.value || checkpointing.value) return;
  checkpointing.value = true;
  try {
    const res = await templatesApi.checkpointTemplate(editing.value.id);
    historyEntries.value = await templatesApi.listTemplateVersions(editing.value.id);
    if (res.template) {
      editing.value = ensureFields(JSON.parse(JSON.stringify(res.template)));
      editingPristine.value = JSON.stringify(editing.value);
    }
  } catch (err) {
    window.alert('Checkpoint failed: ' + (err.message || err));
  } finally {
    checkpointing.value = false;
  }
}

async function restoreVersion(version) {
  if (!editing.value || restoring.value) return;
  if (!window.confirm(`Restore version ${version}? Your current edits will be saved as a new version first if checkpointed.`)) return;
  restoring.value = true;
  try {
    const res = await templatesApi.restoreTemplateVersion(editing.value.id, version);
    historyEntries.value = await templatesApi.listTemplateVersions(editing.value.id);
    if (res.template) {
      editing.value = ensureFields(JSON.parse(JSON.stringify(res.template)));
      editingPristine.value = JSON.stringify(editing.value);
      // Refresh the store list too so the sidebar reflects the restored state
      await store.fetchTemplates();
    }
  } catch (err) {
    window.alert('Restore failed: ' + (err.message || err));
  } finally {
    restoring.value = false;
  }
}

function ensureFields(t) {
  if (!t.variables) t.variables = {};
  if (!t.characters) t.characters = [];
  if (!t.maskedIntents) t.maskedIntents = [];
  if (!t.milestones) t.milestones = [];
  return t;
}

function formatDate(iso) {
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

// Bumped only when the user uploads/removes an image. Without this, evaluating
// Date.now() inside imgUrl during every reactive re-render generated a fresh
// URL per render for every card, saturating the browser's HTTP/1.1 connection
// pool and starving JS chunk + activity polling fetches.
const imageBumps = reactive(new Map());

function imgUrl(template) {
  const base = templatesApi.templateImageUrl(template);
  if (!base) return null;
  const bump = imageBumps.get(template.id);
  return bump ? `${base}&t=${bump}` : base;
}

async function onImageChosen(event) {
  const file = event.target.files?.[0];
  if (!file || !editing.value || isNew.value) return;
  imageUploading.value = true;
  try {
    const res = await templatesApi.uploadTemplateImage(editing.value.id, file);
    if (res.template) {
      editing.value.coverImage = res.template.coverImage;
      // Reflect into the store list too
      const idx = store.templates.findIndex(t => t.id === editing.value.id);
      if (idx >= 0) store.templates[idx].coverImage = res.template.coverImage;
      imageBumps.set(editing.value.id, Date.now());
    }
  } catch (err) {
    window.alert('Image upload failed: ' + (err.message || err));
  } finally {
    imageUploading.value = false;
    if (imageInput.value) imageInput.value.value = '';
  }
}

async function removeImage() {
  if (!editing.value || isNew.value) return;
  imageUploading.value = true;
  try {
    await templatesApi.deleteTemplateImage(editing.value.id);
    editing.value.coverImage = null;
    const idx = store.templates.findIndex(t => t.id === editing.value.id);
    if (idx >= 0) delete store.templates[idx].coverImage;
    imageBumps.delete(editing.value.id);
  } catch (err) {
    window.alert('Could not remove image: ' + (err.message || err));
  } finally {
    imageUploading.value = false;
  }
}

// Track chub-imports we kicked off from THIS view so we can auto-open the
// resulting template in the editor once the job finishes — but only if the
// user is still on this view. (App.vue handles the global "refresh sidebar"
// concern: that runs even if the user has navigated away.)
const pendingImportJobs = ref({});  // { jobId: true }

function onImportQueued({ jobId }) {
  showImport.value = false;
  pendingImportJobs.value[jobId] = true;
}

watch(() => jobs.jobs, async (current) => {
  for (const jobId of Object.keys(pendingImportJobs.value)) {
    const j = current.find(x => x.id === jobId);
    if (!j) continue;
    if (j.status !== 'done' && j.status !== 'cancelled' && j.status !== 'error') continue;

    delete pendingImportJobs.value[jobId];
    if (j.status !== 'done') continue;

    // Pull the saved template from the job's result and open it.
    try {
      const resp = await fetch(`/api/jobs/${jobId}`);
      if (!resp.ok) continue;
      const detail = await resp.json();
      const tpl = detail?.result?.template;
      if (!tpl) continue;
      editing.value = ensureFields(JSON.parse(JSON.stringify(tpl)));
      editingPristine.value = JSON.stringify(editing.value);
      isNew.value = false;
      expandedDiffs.value = {};
      diffCache.value = {};
      diffLoading.value = {};
      loadSources();
    } catch { /* App.vue already refreshed the sidebar; user can click in */ }
  }
}, { deep: true });

onMounted(() => store.fetchTemplates());

function edit(tpl) {
  editing.value = ensureFields(JSON.parse(JSON.stringify(tpl)));
  editingPristine.value = JSON.stringify(editing.value);
  isNew.value = false;
  expandedDiffs.value = {};
  diffCache.value = {};
  diffLoading.value = {};
  loadSources();
}

function duplicate(tpl) {
  const copy = JSON.parse(JSON.stringify(tpl));
  copy.id = copy.id + '_copy';
  copy.name = copy.name + ' (copy)';
  if (!copy.variables) copy.variables = {};
  if (!copy.characters) copy.characters = [];
  if (!copy.maskedIntents) copy.maskedIntents = [];
  if (!copy.milestones) copy.milestones = [];
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
    characters: [],
    maskedIntents: [],
    milestones: [],
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
  editing.value.milestones = (editing.value.milestones || []).filter(m => m.trim());
  const saved = await store.saveTemplate(editing.value);
  if (saved) {
    editing.value = ensureFields(JSON.parse(JSON.stringify(saved)));
    editingPristine.value = JSON.stringify(editing.value);
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
