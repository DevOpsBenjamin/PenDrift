import MarkdownIt from 'markdown-it';

/**
 * Custom markdown-it renderer for narrative prose.
 *
 * Conventions for the LLM:
 * - "Dialogue in double quotes" → warm dialogue color
 * - *Italic text* → inner thoughts / emphasis
 * - **Bold text** → strong emphasis / key moments
 * - 'Single quote text' → internal monologue (muted)
 * - --- → scene break
 * - Regular paragraphs → narrative prose
 */

const md = new MarkdownIt({
  html: false,
  breaks: true,
  typographer: false,
});

md.renderer.rules.text = (tokens, idx) => {
  let content = tokens[idx].content;

  // Style "dialogue" — double quotes
  content = content.replace(
    /"([^"]+)"/g,
    '<span class="narrative-dialogue">\u201C$1\u201D</span>'
  );

  // Also handle smart quotes already in text
  content = content.replace(
    /\u201C([^\u201D]+)\u201D/g,
    (match, inner) => {
      if (match.includes('narrative-dialogue')) return match;
      return `<span class="narrative-dialogue">\u201C${inner}\u201D</span>`;
    }
  );

  // Style 'inner monologue' — single quotes
  content = content.replace(
    /(?<!\w)'([^']+)'(?!\w)/g,
    '<span class="narrative-thought">\u2018$1\u2019</span>'
  );

  return content;
};

md.renderer.rules.hr = () => {
  return '<div class="narrative-scene-break"><span></span></div>';
};

export function renderNarrative(text) {
  if (!text) return '';
  return md.render(text);
}
