import { defineStore } from 'pinia';
import * as generateApi from '../api/generate.js';
import * as charactersApi from '../api/characters.js';
import api from '../api/client.js';

export const useNarrativeStore = defineStore('narrative', {
  state: () => ({
    chunks: [],
    chapters: [],
    currentChapterId: null,
    characters: [],
    generating: false,
    characterUpdatePending: false,
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
    setChapters(chapters) {
      this.chapters = chapters;
      if (!this.currentChapterId && chapters.length > 0) {
        this.currentChapterId = chapters[0].id;
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
        const result = await generateApi.generate(sessionId, {
          chapterId: this.currentChapterId,
          directive,
          isKeyMoment,
        });
        this.chunks.push(result.chunk);

        if (result.characterUpdatePending) {
          this.characterUpdatePending = true;
          this.pollCharacterUpdate(sessionId);
        }

        return result;
      } catch (err) {
        this.error = err.message;
        return null;
      } finally {
        this.generating = false;
      }
    },

    async regenerateLast(sessionId) {
      if (!this.currentChapterId) return;
      this.generating = true;
      this.error = null;
      try {
        const result = await generateApi.regenerate(sessionId, {
          chapterId: this.currentChapterId,
        });
        // Remove last chunk and add the new one
        const idx = this.chunks.findIndex(c => c.chapterId === this.currentChapterId);
        const chapterChunks = this.chunks.filter(c => c.chapterId === this.currentChapterId);
        if (chapterChunks.length > 0) {
          const lastId = chapterChunks[chapterChunks.length - 1].id;
          this.chunks = this.chunks.filter(c => c.id !== lastId);
        }
        this.chunks.push(result.chunk);
        return result;
      } catch (err) {
        this.error = err.message;
        return null;
      } finally {
        this.generating = false;
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

    async pollCharacterUpdate(sessionId) {
      const poll = async () => {
        try {
          const { status } = await charactersApi.getCharacterUpdateStatus(sessionId);
          if (status === 'done' || status === 'failed') {
            this.characterUpdatePending = false;
            if (status === 'done') {
              await this.loadCharacters(sessionId);
            }
          } else {
            setTimeout(poll, 2000);
          }
        } catch {
          this.characterUpdatePending = false;
        }
      };
      setTimeout(poll, 2000);
    },
  },
});
