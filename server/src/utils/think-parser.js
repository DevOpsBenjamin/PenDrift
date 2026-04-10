/**
 * Strips thinking blocks from LLM responses.
 * Block delimiters are configurable per settings preset.
 */
export function stripThinkBlocks(text, startTag = '<think>', endTag = '</think>') {
  if (!text) return { narrative: '', thinking: '' };

  const thinkingParts = [];
  let narrative = text;

  // Escape regex special chars in tags
  const escStart = startTag.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const escEnd = endTag.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  // Match complete think blocks
  const regex = new RegExp(`${escStart}([\\s\\S]*?)${escEnd}`, 'g');
  let match;
  while ((match = regex.exec(narrative)) !== null) {
    thinkingParts.push(match[1].trim());
  }
  narrative = narrative.replace(regex, '');

  // Handle unclosed think block (everything from start tag to end)
  const unclosedIdx = narrative.indexOf(startTag);
  if (unclosedIdx !== -1) {
    thinkingParts.push(narrative.slice(unclosedIdx + startTag.length).trim());
    narrative = narrative.slice(0, unclosedIdx);
  }

  return {
    narrative: narrative.trim(),
    thinking: thinkingParts.join('\n\n'),
  };
}
