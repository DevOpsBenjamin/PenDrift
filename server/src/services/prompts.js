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
 * Builds the messages array for an LLM generation call.
 */
export function buildMessages({ settings, characters, template, chunks, directive }) {
  const messages = [];
  const vars = template?.variables || {};
  const resolve = (text) => resolveVariables(text, vars);

  // 1. System prompt: base + character sheets + masked intents + scenario
  let system = settings.systemPrompt || '';

  // Scenario context
  if (template?.scenario) {
    system += `\n\n## Scenario\n${resolve(template.scenario)}`;
  }

  // Template-specific additions
  if (template?.systemPromptAdditions) {
    system += `\n\n## Style Instructions\n${resolve(template.systemPromptAdditions)}`;
  }

  // Masked intents (hidden narrative drivers)
  if (template?.maskedIntents?.length) {
    system += '\n\n## Hidden Narrative Drivers (never reveal these directly)\n';
    system += template.maskedIntents.map(i => `- ${resolve(i)}`).join('\n');
  }

  // Current character sheets
  if (characters?.length) {
    system += '\n\n## Current Character States\n';
    for (const char of characters) {
      const role = char.isUser ? ' (the director\'s character)' : '';
      system += `\n### ${char.name}${role}\n`;
      system += `State: ${char.currentState}\n`;
      if (char.traits?.length) {
        system += `Traits: ${char.traits.join(', ')}\n`;
      }
      if (char.keyEvents?.length) {
        system += `Key events: ${char.keyEvents.join('; ')}\n`;
      }
    }
  }

  messages.push({ role: 'system', content: system });

  // 2. Previous narrative chunks consolidated into one assistant message
  if (chunks?.length) {
    const narrativeHistory = chunks.map(c => c.narrative).join('\n\n');
    messages.push({ role: 'assistant', content: narrativeHistory });
  }

  // 3. Current directive as user message
  messages.push({ role: 'user', content: directive });

  return messages;
}

/**
 * Builds the messages array for a character sheet meta-call.
 */
export function buildCharacterUpdateMessages({ characters, recentChunks }) {
  const narrativeText = recentChunks.map(c => c.narrative).join('\n\n');

  const system = `You are a narrative analyst. Your job is to analyze recent narrative events and update character sheets to reflect how characters have evolved.

Given the current character sheets and the recent narrative, update each character's sheet. Consider:
- Has their emotional state changed?
- Have they revealed new traits or lost old ones?
- Did any key events happen to them?

Return ONLY valid JSON in this exact format, no other text:
[
  {
    "name": "Character Name",
    "currentState": "updated state description",
    "traits": ["trait1", "trait2"],
    "keyEvents": ["event1", "event2"]
  }
]`;

  const userContent = `## Current Character Sheets
${JSON.stringify(characters, null, 2)}

## Recent Narrative
${narrativeText}

Update the character sheets based on the narrative above. Return only the JSON array.`;

  return [
    { role: 'system', content: system },
    { role: 'user', content: userContent },
  ];
}
