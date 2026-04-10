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

/**
 * Pre-process text to wrap dialogue in markers before markdown parsing.
 * Handles split dialogue across paragraphs and various quote styles.
 */
function preprocessDialogue(text) {
  // Replace straight double quotes pairs
  text = text.replace(/"([^"]+)"/g, '\x01DIAL\x02$1\x01/DIAL\x02');

  // Replace smart double quotes pairs
  text = text.replace(/\u201C([^\u201D]+)\u201D/g, '\x01DIAL\x02$1\x01/DIAL\x02');

  // Handle opening quote without closing on same line — find the closing quote
  // Match "text that continues... across lines... until closing"
  text = text.replace(/"([^"]*?)"/g, '\x01DIAL\x02$1\x01/DIAL\x02');

  return text;
}

/**
 * Post-process HTML to convert dialogue markers to styled spans.
 */
function postprocessDialogue(html) {
  html = html.replace(/\x01DIAL\x02/g, '<span class="narrative-dialogue">\u201C');
  html = html.replace(/\x01\/DIAL\x02/g, '\u201D</span>');
  return html;
}

md.renderer.rules.text = (tokens, idx) => {
  let content = tokens[idx].content;

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
  // Pre-process dialogue markers before markdown
  const processed = preprocessDialogue(text);
  // Render markdown
  let html = md.render(processed);
  // Post-process dialogue markers to styled spans
  html = postprocessDialogue(html);
  return html;
}
