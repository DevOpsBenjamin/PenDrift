"""Extract and strip <think> blocks from LLM output."""
import re


def strip_think_blocks(
    text: str,
    start_tag: str = "<think>",
    end_tag: str = "</think>",
) -> tuple[str, str | None]:
    """Return (narrative, thinking). Handles closed and unclosed blocks."""
    if start_tag not in text:
        return text.strip(), None

    # Closed blocks: <think>...</think>
    pattern = re.escape(start_tag) + r"(.*?)" + re.escape(end_tag)
    thinking_parts: list[str] = []
    narrative = text

    for match in re.finditer(pattern, text, re.DOTALL):
        thinking_parts.append(match.group(1).strip())
        narrative = narrative.replace(match.group(0), "", 1)

    # Unclosed block: <think>... (rest of text)
    if start_tag in narrative:
        idx = narrative.index(start_tag)
        thinking_parts.append(narrative[idx + len(start_tag):].strip())
        narrative = narrative[:idx]

    thinking = "\n\n".join(thinking_parts) if thinking_parts else None
    return narrative.strip(), thinking
