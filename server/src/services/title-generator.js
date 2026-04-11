import { generateCompletion } from './llm.js';
import { getCharacters } from './characters.js';
import { getFacts } from './facts.js';

function getNarrative(chunk) {
  if (chunk.versions?.length) return chunk.versions[chunk.activeVersion ?? 0].narrative;
  return chunk.narrative;
}

/**
 * Generate a chapter title from the LLM using structured excerpts.
 * @param {string} sessionId
 * @param {Array} chunks - all chunks of the chapter
 * @param {Object} settings - settings preset
 * @param {number} chapterOrder - chapter index (for fallback title)
 * @returns {string} generated title
 */
export async function generateChapterTitle(sessionId, chunks, settings, chapterOrder) {
  const fallback = `Chapter ${chapterOrder + 1}`;
  if (!chunks.length) return fallback;

  try {
    const titleMessages = [
      { role: 'system', content: 'You are a chapter title generator for a novel. You will receive excerpts from the beginning, middle, and end of a chapter, plus a meta-analysis summary. Suggest a short, evocative chapter title (3-6 words max). Return ONLY the title, nothing else. No quotes, no explanation.' },
    ];

    // First 2 chunks
    titleMessages.push({ role: 'user', content: 'This is the BEGINNING of the chapter:' });
    titleMessages.push({ role: 'assistant', content: getNarrative(chunks[0]).slice(0, 500) });
    if (chunks.length >= 2) {
      titleMessages.push({ role: 'assistant', content: getNarrative(chunks[1]).slice(0, 500) });
    }

    // Middle chunk
    if (chunks.length >= 5) {
      const midIdx = Math.floor(chunks.length / 2);
      titleMessages.push({ role: 'user', content: 'This is the MIDDLE of the chapter:' });
      titleMessages.push({ role: 'assistant', content: getNarrative(chunks[midIdx]).slice(0, 500) });
    }

    // Last 2 chunks
    if (chunks.length >= 3) {
      titleMessages.push({ role: 'user', content: 'This is the END of the chapter:' });
      if (chunks.length >= 4) {
        titleMessages.push({ role: 'assistant', content: getNarrative(chunks[chunks.length - 2]).slice(0, 500) });
      }
      titleMessages.push({ role: 'assistant', content: getNarrative(chunks[chunks.length - 1]).slice(0, 500) });
    }

    // Meta summary
    const characters = await getCharacters(sessionId);
    const importantFacts = await getFacts(sessionId);
    let metaSummary = 'Meta-analysis summary:\n';
    metaSummary += 'Characters: ' + characters.map(c => `${c.name} (${c.currentState})`).join('; ') + '\n';
    if (importantFacts.length) {
      metaSummary += 'Key facts: ' + importantFacts.slice(-5).join('; ');
    }
    titleMessages.push({ role: 'user', content: metaSummary + '\n\nBased on all of the above, suggest a chapter title.' });

    const metaModel = settings.metaModel || settings.narrativeModel;
    const titleSettings = { ...settings, maxTokens: (settings.maxTokens || 1024) * 2 };
    const { narrative: titleResult } = await generateCompletion(titleMessages, titleSettings, metaModel, sessionId, 'title');

    if (titleResult && titleResult.length < 80) {
      return titleResult.replace(/["']/g, '').trim();
    }
  } catch (err) {
    console.error('[TitleGen] Failed:', err.message);
  }

  return fallback;
}
