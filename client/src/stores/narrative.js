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
    activeJobId: null,
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
    setChapters(sessionId, chapters) {
      this.currentSessionId = sessionId;
      this.chapters = chapters;
      const validId = chapters.find(c => c.id === this.currentChapterId);
      if (!validId && chapters.length > 0) {
        this.currentChapterId = chapters[0].id;
      }
      this.chunks = [];
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
        this.activeJobId = jobId;
        // Poll for result
        this.pollJob(sessionId, jobId);
      } catch (err) {
        this.error = err.message;
        this.generating = false;
      }
    },

    async regenerateLast(sessionId) {
      if (!this.currentChapterId) return;
      this.generating = true;
      this.error = null;
      try {
        // Remove last chunk from UI immediately
        const chapterChunks = this.chunks.filter(c => c.chapterId === this.currentChapterId);
        if (chapterChunks.length > 0) {
          const lastId = chapterChunks[chapterChunks.length - 1].id;
          this.chunks = this.chunks.filter(c => c.id !== lastId);
        }

        const { jobId } = await generateApi.startRegeneration(sessionId, {
          chapterId: this.currentChapterId,
        });
        this.activeJobId = jobId;
        this.pollJob(sessionId, jobId);
      } catch (err) {
        this.error = err.message;
        this.generating = false;
        // Reload chapter to restore state on error
        await this.loadChapter(sessionId, this.currentChapterId);
      }
    },

    async deleteLastChunk(sessionId) {
      if (!this.currentChapterId) return;
      this.error = null;
      try {
        await generateApi.deleteLastChunk(sessionId, this.currentChapterId);
        const chapterChunks = this.chunks.filter(c => c.chapterId === this.currentChapterId);
        if (chapterChunks.length > 0) {
          const lastId = chapterChunks[chapterChunks.length - 1].id;
          this.chunks = this.chunks.filter(c => c.id !== lastId);
        }
      } catch (err) {
        this.error = err.message;
      }
    },

    pollJob(sessionId, jobId) {
      const poll = async () => {
        // Stop polling if user navigated away or job changed
        if (this.activeJobId !== jobId) return;

        try {
          const job = await generateApi.getJobStatus(sessionId, jobId);

          if (job.status === 'done') {
            this.generating = false;
            this.activeJobId = null;

            if (job.result?.chunk) {
              // Only append if we're still on the same session/chapter
              if (this.currentSessionId === sessionId) {
                this.chunks.push(job.result.chunk);
              }
            }

            if (job.result?.metaUpdatePending) {
              this.metaUpdatePending = true;
              this.pollMetaStatus(sessionId);
            }
          } else if (job.status === 'failed') {
            this.generating = false;
            this.activeJobId = null;
            this.error = job.error || 'Generation failed';
          } else {
            // Still generating, poll again
            setTimeout(poll, 2000);
          }
        } catch {
          this.generating = false;
          this.activeJobId = null;
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
