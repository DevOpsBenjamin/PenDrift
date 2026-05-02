import { defineStore } from 'pinia';
import * as generateApi from '../api/generate.js';
import * as charactersApi from '../api/characters.js';
import api from '../api/client.js';

export const useNarrativeStore = defineStore('narrative', {
  state: () => ({
    chunks: [],
    chapters: [],
    currentChapterId: null,
    currentSessionId: null,
    characters: [],
    consistencyFlags: [],
    generating: false,
    activeJobs: {},  // { sessionId: jobId } — legacy job-based fallback
    metaUpdatePending: false,
    error: null,
    // Streaming state (SSE-backed) — only one stream per session at a time
    streamPhase: 'idle',  // 'idle' | 'preparing' | 'meta_running' | 'loading_model' | 'thinking' | 'narrative' | 'done' | 'error'
    liveThinking: '',
    liveNarrative: '',
    liveSuggestions: [],
    modelLoadingPath: '',
    metaSummary: null,    // {charactersUpdated, newCharacters, factsCount, consistencyFlags} after meta_done
    metaHistory: [],      // meta-analysis runs for the current session, shown as dividers between chunks
    streamAbort: null,    // AbortController for cancellation
    pendingDirective: '', // text the user wants prefilled into DirectiveInput (e.g. clicked suggestion)
  }),

  getters: {
    currentChapterChunks: (state) =>
      state.chunks.filter(c => c.chapterId === state.currentChapterId),

    lastChunk() {
      const chunks = this.currentChapterChunks;
      return chunks[chunks.length - 1] || null;
    },
  },

  actions: {
    isSessionGenerating(sessionId) {
      return !!this.activeJobs[sessionId || this.currentSessionId];
    },

    setChapters(sessionId, chapters) {
      this.currentSessionId = sessionId;
      this.chapters = chapters;
      const validId = chapters.find(c => c.id === this.currentChapterId);
      if (!validId && chapters.length > 0) {
        this.currentChapterId = chapters[0].id;
      }
      this.chunks = [];
      // Resume polling if this session has an active job
      const existingJob = this.activeJobs[sessionId];
      if (existingJob) {
        this.generating = true;
        this.pollJob(sessionId, existingJob);
      } else {
        this.generating = false;
      }
    },

    async loadChapter(sessionId, chapterId) {
      this.currentChapterId = chapterId;
      this.error = null;
      try {
        const res = await api.get(`sessions/${sessionId}/chapters/${chapterId}`).json();
        this.chunks = res.chunks || [];
      } catch (err) {
        this.error = err.message;
      }
    },

    async loadCharacters(sessionId) {
      try {
        this.characters = await charactersApi.getCharacters(sessionId);
      } catch (err) {
        this.error = err.message;
      }
    },

    async loadMetaHistory(sessionId) {
      try {
        this.metaHistory = await charactersApi.getMetaHistory(sessionId);
      } catch { /* not critical */ }
    },

    async generate(sessionId, directive, isKeyMoment = false) {
      if (!this.currentChapterId) return;
      this.generating = true;
      this.error = null;
      this.streamPhase = 'thinking';
      this.liveThinking = '';
      this.liveNarrative = '';
      this.liveSuggestions = [];
      this.metaSummary = null;

      const controller = new AbortController();
      this.streamAbort = controller;

      // Streaming may start with prep (settings, meta) before any model token.
      // Set initial phase to 'preparing' so the UI doesn't pretend we're already
      // in the model's thinking phase while the backend is doing meta-analysis.
      this.streamPhase = 'preparing';

      try {
        await generateApi.streamGeneration(
          sessionId,
          { chapterId: this.currentChapterId, directive, isKeyMoment },
          (ev) => this._handleStreamEvent(sessionId, ev),
          controller.signal,
        );
      } catch (err) {
        if (err.name !== 'AbortError') {
          this.error = err.message || 'Stream failed';
          this.streamPhase = 'error';
        }
      } finally {
        this.generating = false;
        this.streamAbort = null;
      }
    },

    prefillDirective(text) {
      // Push text into the DirectiveInput. Cleared once consumed.
      this.pendingDirective = text || '';
    },

    /** The director clicked a suggestion the model emitted on the last chunk.
     * Auto-submits a framed directive that tells the model the director is
     * choosing a path, not writing one — keep narrating in the same voice and
     * keep proposing options for the next pause point. */
    async chooseSuggestion(suggestion) {
      if (!this.currentSessionId || !this.currentChapterId) return;
      const text = (suggestion || '').trim();
      if (!text) return;
      const framed = (
        `[Director chose your suggestion: "${text}"]\n\n` +
        `Continue the narrative in this direction. Match the tone, pacing, POV, and voice ` +
        `of the previous chunk — the director is HAPPY to be guided and prefers reading ` +
        `over writing. Keep agency with the characters: do NOT prompt the director with a ` +
        `question, do NOT ask "what does X do?", just keep narrating as if you were a novelist ` +
        `and the director is your reader. Always include 2-4 fresh suggestions at the next ` +
        `natural pause so they can keep choosing.`
      );
      await this.generate(this.currentSessionId, framed, false);
    },

    cancelStream() {
      if (this.streamAbort) {
        this.streamAbort.abort();
        this.streamAbort = null;
      }
    },

    /**
     * On session/page load, check if a generation is already in flight for
     * this session and re-attach the live UI to it (replay buffered events +
     * receive live updates).
     */
    async tryAttachStream(sessionId) {
      try {
        const status = await generateApi.getActiveStreamStatus(sessionId);
        if (!status.running || status.done) return;
      } catch {
        return;
      }

      // Open the attach SSE — replays past events, then live ones.
      this.generating = true;
      this.error = null;
      this.streamPhase = 'thinking';  // will be corrected by replayed events
      this.liveThinking = '';
      this.liveNarrative = '';
      this.liveSuggestions = [];

      const controller = new AbortController();
      this.streamAbort = controller;
      try {
        await generateApi.attachGenerationStream(
          sessionId,
          (ev) => this._handleStreamEvent(sessionId, ev),
          controller.signal,
        );
      } catch (err) {
        if (err.name !== 'AbortError') {
          // 404 (gen finished between status check and attach) or transport error
          this.streamPhase = 'idle';
        }
      } finally {
        this.generating = false;
        this.streamAbort = null;
      }
    },

    _handleStreamEvent(sessionId, ev) {
      switch (ev.type) {
        case 'meta_starting':
          this.streamPhase = 'meta_running';
          this.metaSummary = null;
          this.metaUpdatePending = true;
          break;
        case 'meta_done':
          this.metaSummary = ev.error ? null : {
            charactersUpdated: ev.charactersUpdated || 0,
            newCharacters: ev.newCharacters || 0,
            factsCount: ev.factsCount || 0,
            consistencyFlags: ev.consistencyFlags || 0,
          };
          this.metaUpdatePending = false;
          this.streamPhase = 'preparing';
          // Reload characters and meta history now that they may have changed
          this.loadCharacters(sessionId);
          this.loadMetaHistory(sessionId);
          break;
        case 'prep_done':
          // After prep, we're about to call the model. If we don't get a model_loading
          // event next, the streaming will start soon — switch back to a thinking-ish
          // pre-state to let the spinner take over.
          if (this.streamPhase !== 'loading_model') {
            this.streamPhase = 'thinking';
          }
          break;
        case 'model_loading':
          this.streamPhase = 'loading_model';
          this.modelLoadingPath = ev.modelPath || '';
          break;
        case 'model_loaded':
          this.modelLoadingPath = '';
          this.streamPhase = 'thinking';
          break;
        case 'started':
          // stream_narrative entered running state
          break;
        case 'thinking_start':
          this.streamPhase = 'thinking';
          this.liveThinking = '';
          break;
        case 'thinking_chunk':
          this.liveThinking += ev.text || '';
          break;
        case 'thinking_done':
          // Keep liveThinking in state — UI may move it to brain panel
          break;
        case 'type_resolved':
          // 'narrative' or 'suggestion'
          break;
        case 'narrative_start':
          this.streamPhase = 'narrative';
          this.liveNarrative = '';
          break;
        case 'narrative_chunk':
          this.liveNarrative += ev.text || '';
          break;
        case 'narrative_done':
          break;
        case 'suggestions':
          this.liveSuggestions = ev.items || [];
          break;
        case 'done':
          if (ev.kind === 'narrative' && ev.chunk && this.currentSessionId === sessionId) {
            const existing = this.chunks.find(c => c.id === ev.chunk.id);
            if (existing) {
              existing.versions = ev.chunk.versions;
              existing.activeVersion = ev.chunk.activeVersion;
            } else {
              this.chunks.push(ev.chunk);
            }
          }
          if (ev.metaUpdatePending) {
            this.metaUpdatePending = true;
            this.pollMetaStatus(sessionId);
          }
          // Hand off live → finalized chunk in one tick to avoid visual stutter
          this.streamPhase = 'idle';
          this.liveThinking = '';
          this.liveNarrative = '';
          this.liveSuggestions = [];
          break;
        case 'error':
          this.streamPhase = 'error';
          this.error = ev.message || 'Generation error';
          break;
      }
    },

    async regenerateChunk(sessionId, chunkId, directive) {
      if (!this.currentChapterId) return;
      this.generating = true;
      this.error = null;
      this.streamPhase = 'thinking';
      this.liveThinking = '';
      this.liveNarrative = '';
      this.liveSuggestions = [];
      this.metaSummary = null;

      const controller = new AbortController();
      this.streamAbort = controller;

      try {
        await generateApi.streamRegeneration(
          sessionId,
          { chunkId, directive },
          (ev) => this._handleStreamEvent(sessionId, ev),
          controller.signal,
        );
      } catch (err) {
        if (err.name !== 'AbortError') {
          this.error = err.message || 'Regenerate stream failed';
          this.streamPhase = 'error';
        }
      } finally {
        this.generating = false;
        this.streamAbort = null;
      }
    },

    async deleteVersion(sessionId, chunkId) {
      this.error = null;
      try {
        const chunk = this.chunks.find(c => c.id === chunkId);
        const versionIndex = chunk?.activeVersion ?? 0;
        const result = await generateApi.deleteChunkVersion(sessionId, chunkId, versionIndex);
        if (result.deleted === 'chunk') {
          this.chunks = this.chunks.filter(c => c.id !== chunkId);
        } else if (result.chunk) {
          chunk.versions = result.chunk.versions;
          chunk.activeVersion = result.chunk.activeVersion;
        }
      } catch (err) {
        this.error = err.message;
      }
    },

    pollJob(sessionId, jobId) {
      const poll = async () => {
        // Stop polling if job was replaced
        if (this.activeJobs[sessionId] !== jobId) return;

        try {
          const job = await generateApi.getJobStatus(sessionId, jobId);

          if (job.status === 'done') {
            delete this.activeJobs[sessionId];
            if (this.currentSessionId === sessionId) {
              this.generating = false;
            }

            if (job.result?.chunk) {
              if (this.currentSessionId === sessionId) {
                // Check if this is a version update (regenerate) or a new chunk
                const existing = this.chunks.find(c => c.id === job.result.chunk.id);
                if (existing) {
                  // Update existing chunk with new versions
                  existing.versions = job.result.chunk.versions;
                  existing.activeVersion = job.result.chunk.activeVersion;
                } else {
                  // New chunk
                  this.chunks.push(job.result.chunk);
                }
              }
            }

            if (job.result?.metaUpdatePending) {
              this.metaUpdatePending = true;
              this.pollMetaStatus(sessionId);
            }
          } else if (job.status === 'failed') {
            delete this.activeJobs[sessionId];
            if (this.currentSessionId === sessionId) {
              this.generating = false;
              this.error = job.error || 'Generation failed';
            }
          } else {
            // Still generating, poll again
            setTimeout(poll, 2000);
          }
        } catch (err) {
          console.warn('[PenDrift] Poll error:', err.message || err);
          // Retry a few times before giving up (server might have restarted)
          pollRetries++;
          if (pollRetries < 5) {
            setTimeout(poll, 3000);
          } else {
            delete this.activeJobs[sessionId];
            if (this.currentSessionId === sessionId) {
              this.generating = false;
              this.error = 'Lost connection to generation job. Refresh to check results.';
            }
          }
        }
      };
      let pollRetries = 0;
      setTimeout(poll, 1000);
    },

    pollMetaStatus(sessionId) {
      const poll = async () => {
        try {
          const meta = await api.get(`sessions/${sessionId}/meta/status`).json();
          if (meta.status === 'done' || meta.status === 'failed') {
            this.metaUpdatePending = false;
            if (meta.status === 'done' && meta.result) {
              await this.loadCharacters(sessionId);
              if (meta.result.consistencyFlags?.length) {
                this.consistencyFlags = meta.result.consistencyFlags;
              }
            }
          } else {
            setTimeout(poll, 2000);
          }
        } catch {
          this.metaUpdatePending = false;
        }
      };
      setTimeout(poll, 2000);
    },
  },
});
