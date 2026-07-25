from __future__ import annotations

from typing import Any

_DEFAULT_MAX_WORDS = 60


class PromptCompressor:
    """Shortens an over-long PromptPackage.positive_prompt: first by
    deduplicating repeated comma-separated fragments (the most common
    source of bloat when several context sources independently mention
    the same subject), then, if still over budget, by truncating to
    `max_words` words. Never touches negative_prompt - a shorter
    negative prompt isn't meaningfully cheaper and dropping a guardrail
    term to save space is the wrong tradeoff."""

    def compress(self, package: dict[str, Any], max_words: int = _DEFAULT_MAX_WORDS) -> dict[str, Any]:
        positive_prompt = package["positive_prompt"]
        if len(positive_prompt.split()) <= max_words:
            return package

        fragments = [f.strip() for f in positive_prompt.split(",") if f.strip()]
        deduped: list[str] = []
        seen: set[str] = set()
        for fragment in fragments:
            key = fragment.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(fragment)
        compressed_prompt = ", ".join(deduped)

        words = compressed_prompt.split()
        if len(words) > max_words:
            compressed_prompt = " ".join(words[:max_words]) + "..."

        return {**package, "positive_prompt": compressed_prompt, "compressed": True}
