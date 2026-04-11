/**
 * Replaces all {{variable}} placeholders using the template's variables map.
 */
function resolveVariables(text, variables) {
  if (!text || !variables) return text;
  return text.replace(/\{\{(\w+)\}\}/g, (match, key) => {
    return variables[key] !== undefined ? variables[key] : match;
  });
}

/**
 * Gets the active narrative text from a chunk (versioned or legacy).
 */
function getChunkNarrative(chunk) {
  if (chunk.versions?.length) {
    return chunk.versions[chunk.activeVersion ?? 0].narrative;
  }
  return chunk.narrative;
}

/**
 * Builds the messages array for an LLM generation call.
 *
 * Structure:
 *   system: [prompt + sheets + facts]
 *   user: "Begin."
 *   assistant: [chunk 1]
 *   assistant: [chunk 2]
 *   ...
 *   assistant: [chunk N]  (where meta was run after chunk N)
 *   user: "[Character sheets updated]"  (meta marker, if applicable)
 *   assistant: [chunk N+1]
 *   ...
 *   assistant: [last chunk]
 *   user: [directive]
 *
 * Only sends the last `chunkUpdateInterval` chunks (rolling window).
 * Meta marker inserted between chunks where the meta-analysis was performed.
 */
export function buildMessages({ settings, characters, template, chunks, directive, importantFacts, lastMetaAfterChunkIndex, previousChapterChunks }) {
  const messages = [];
  const vars = template?.variables || {};
  const resolve = (text) => resolveVariables(text, vars);

  // 1. System prompt
  let system = settings.narrativePrompt || settings.systemPrompt || '';

  if (template?.scenario) {
    system += `\n\n## Scenario\n${resolve(template.scenario)}`;
  }

  if (template?.systemPromptAdditions) {
    system += `\n\n## Style Instructions\n${resolve(template.systemPromptAdditions)}`;
  }

  if (template?.maskedIntents?.length) {
    system += '\n\n## Hidden Narrative Drivers (never reveal these directly)\n';
    system += template.maskedIntents.map(i => `- ${resolve(i)}`).join('\n');
  }

  if (characters?.length) {
    system += '\n\n## Current Character States\n';
    for (const char of characters) {
      system += `\n### ${char.name}\n`;
      system += `State: ${char.currentState}\n`;
      if (char.traits?.length) {
        system += `Traits: ${char.traits.join(', ')}\n`;
      }
      if (char.keyEvents?.length) {
        system += `Key events: ${char.keyEvents.join('; ')}\n`;
      }
    }
  }

  if (importantFacts?.length) {
    system += '\n\n## Established Facts\n';
    system += importantFacts.map(f => `- ${f}`).join('\n');
  }

  messages.push({ role: 'system', content: system });

  // 2. Rolling window of recent chunks as individual assistant messages
  const interval = settings.chunkUpdateInterval || 10;
  const recentChunks = chunks?.slice(-interval) || [];

  // Cross-chapter context: if current chapter is empty, include last 2 chunks from previous chapter
  if (recentChunks.length === 0 && previousChapterChunks?.length) {
    const crossChunks = previousChapterChunks.slice(-2);
    messages.push({ role: 'user', content: 'Context from the end of the previous chapter:' });
    for (const c of crossChunks) {
      messages.push({ role: 'assistant', content: getChunkNarrative(c) });
    }
  }

  if (recentChunks.length) {
    // Opening user message (required before first assistant)
    messages.push({ role: 'user', content: 'Begin.' });

    // Find where to insert meta marker within our window
    // lastMetaAfterChunkIndex is the global chunk index after which meta was run
    const windowStart = (chunks?.length || 0) - recentChunks.length;

    for (let i = 0; i < recentChunks.length; i++) {
      const globalIndex = windowStart + i;

      messages.push({ role: 'assistant', content: getChunkNarrative(recentChunks[i]) });

      // Insert meta marker after this chunk if meta was run here
      if (lastMetaAfterChunkIndex != null && globalIndex === lastMetaAfterChunkIndex) {
        messages.push({
          role: 'user',
          content: 'Character sheets and established facts have been updated based on the narrative so far. The character states above reflect the story up to this point.',
        });
      }
    }
  }

  // 3. Directive
  messages.push({ role: 'user', content: directive });

  return messages;
}

/**
 * Builds the messages array for the enriched meta-call.
 */
export function buildMetaAnalysisMessages({ characters, recentChunks, importantFacts, metaPrompt, previousMetaResults }) {
  const messages = [];

  // 1. System prompt
  messages.push({ role: 'system', content: metaPrompt || 'You are a narrative analyst. Return only valid JSON.' });

  // 2. Current character sheets
  messages.push({
    role: 'user',
    content: 'Here are the current character sheets. Update them based on the narrative that follows.',
  });
  messages.push({
    role: 'assistant',
    content: JSON.stringify(characters, null, 2),
  });

  // 3. Established facts
  if (importantFacts?.length) {
    messages.push({
      role: 'user',
      content: 'Here are the established facts. Keep all of them, only add new ones. Deduplicate if needed.',
    });
    messages.push({
      role: 'assistant',
      content: importantFacts.map(f => `- ${f}`).join('\n'),
    });
  }

  // 4. Previous meta-analysis results (summaries only)
  if (previousMetaResults?.length) {
    let summary = 'Previous analyses for reference (build on these):\n';
    for (const meta of previousMetaResults) {
      if (meta.result?.characterUpdates?.length) {
        summary += '\nUpdates: ' + meta.result.characterUpdates.map(c => `${c.name}: ${c.currentState}`).join('; ');
      }
      if (meta.result?.importantFacts?.length) {
        summary += '\nFacts: ' + meta.result.importantFacts.join('; ');
      }
    }
    messages.push({ role: 'user', content: summary });
  }

  // 5. Recent narrative chunks — each as its own assistant message
  messages.push({
    role: 'user',
    content: 'Here is the recent narrative to analyze:',
  });
  for (const chunk of recentChunks) {
    messages.push({ role: 'assistant', content: getChunkNarrative(chunk) });
  }

  // 6. Final instruction
  messages.push({
    role: 'user',
    content: 'Analyze the narrative above. Update characters, detect new ones, flag inconsistencies, extract facts. Return ONLY the JSON object.',
  });

  return messages;
}
