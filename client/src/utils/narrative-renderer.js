import MarkdownIt from 'markdown-it';

/**
 * Custom markdown-it renderer for narrative prose.
 *
 * Conventions for the LLM:
 * - "Dialogue in double quotes" → styled as speech
 * - *Italic text* → inner thoughts / emphasis
 * - **Bold text** → strong emphasis / key moments
 * - 'Single quote text' → internal monologue
 * - --- → scene break
 * - Regular paragraphs → narrative prose
 */

const md = new MarkdownIt({
  html: false,
  breaks: true,      // Convert \n to <br>
  typographer: true,  // Smart quotes, dashes
});

// Custom rule: wrap "double quoted dialogue" in a span
const defaultTextRenderer = md.renderer.rules.text || ((tokens, idx) => tokens[idx].content);

md.renderer.rules.text = (tokens, idx, options, env, self) => {
  let content = tokens[idx].content;

  // Style "dialogue" — double quotes
  content = content.replace(
    /"([^"]+)"/g,
    '<span class="narrative-dialogue">\u201C$1\u201D</span>'
  );

  // Style 'inner monologue' — single quotes used for thoughts
  content = content.replace(
    /(?<!\w)'([^']+)'(?!\w)/g,
    '<span class="narrative-thought">\u2018$1\u2019</span>'
  );

  return content;
};

// Style horizontal rules as scene breaks
md.renderer.rules.hr = () => {
  return '<div class="narrative-scene-break"><span></span></div>';
};

export function renderNarrative(text) {
  if (!text) return '';
  return md.render(text);
}
