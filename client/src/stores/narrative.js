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
    activeJobs: {},  // { sessionId: jobId }
    metaUpdatePending: false,
    error: null,
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

    async generate(sessionId, directive, isKeyMoment = false) {
      if (!this.currentChapterId) return;
      this.generating = true;
      this.error = null;
      try {
        // Start job — returns immediately
        const { jobId } = await generateApi.startGeneration(sessionId, {
          chapterId: this.currentChapterId,
          directive,
          isKeyMoment,
        });
        this.activeJobs[sessionId] = jobId;
        this.pollJob(sessionId, jobId);
      } catch (err) {
        this.error = err.message;
        this.generating = false;
      }
    },

    async regenerateChunk(sessionId, chunkId, directive) {
      if (!this.currentChapterId) return;
      this.generating = true;
      this.error = null;
      try {
        const { jobId } = await generateApi.startRegeneration(sessionId, {
          chunkId,
          chapterId: this.currentChapterId,
          directive,
        });
        this.activeJobs[sessionId] = jobId;
        this.pollJob(sessionId, jobId);
      } catch (err) {
        this.error = err.message;
        this.generating = false;
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
        } catch {
          delete this.activeJobs[sessionId];
          if (this.currentSessionId === sessionId) {
            this.generating = false;
          }
        }
      };
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
