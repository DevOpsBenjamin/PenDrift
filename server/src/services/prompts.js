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
export function buildMessages({ settings, characters, template, chunks, directive, importantFacts, lastMetaAfterChunkIndex }) {
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
  const narrativeText = recentChunks.map(c => getChunkNarrative(c)).join('\n\n');

  const system = metaPrompt || `You are a narrative analyst. Analyze recent narrative events and maintain story consistency.

Your tasks:
1. UPDATE existing character sheets to reflect how they have evolved
2. DETECT any new characters mentioned in the narrative and create sheets for them
3. FLAG any consistency issues (name changes, contradictions, forgotten facts)
4. EXTRACT important facts established in the narrative (locations, relationships, promises, secrets)

Return ONLY valid JSON in this exact format, no other text:
{
  "characterUpdates": [
    { "name": "Character Name", "currentState": "updated state", "traits": ["trait1"], "keyEvents": ["event1"] }
  ],
  "newCharacters": [
    { "name": "New Char", "currentState": "state", "traits": [], "keyEvents": ["first mentioned context"] }
  ],
  "consistencyFlags": ["any inconsistencies found"],
  "importantFacts": ["key facts established in the narrative"]
}`;

  let userContent = `## Current Character Sheets\n${JSON.stringify(characters, null, 2)}`;

  if (importantFacts?.length) {
    userContent += `\n\n## Previously Established Facts\n${importantFacts.map(f => `- ${f}`).join('\n')}`;
  }

  // Include previous meta-analysis results for continuity
  if (previousMetaResults?.length) {
    userContent += '\n\n## Previous Meta-Analysis Results (for reference — build on these, don\'t lose information)';
    for (const meta of previousMetaResults) {
      userContent += `\n\n### Analysis at ${meta.timestamp}`;
      if (meta.result?.characterUpdates?.length) {
        userContent += '\nCharacter updates: ' + meta.result.characterUpdates.map(c => `${c.name}: ${c.currentState}`).join('; ');
      }
      if (meta.result?.newCharacters?.length) {
        userContent += '\nNew characters: ' + meta.result.newCharacters.map(c => c.name).join(', ');
      }
      if (meta.result?.importantFacts?.length) {
        userContent += '\nFacts found: ' + meta.result.importantFacts.join('; ');
      }
      if (meta.result?.consistencyFlags?.length) {
        userContent += '\nFlags: ' + meta.result.consistencyFlags.join('; ');
      }
    }
  }

  userContent += `\n\n## Recent Narrative\n${narrativeText}`;
  userContent += '\n\nAnalyze the narrative above. Return only the JSON object.';

  return [
    { role: 'system', content: system },
    { role: 'user', content: userContent },
  ];
}
