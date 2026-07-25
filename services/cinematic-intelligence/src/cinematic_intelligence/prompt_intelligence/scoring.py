from __future__ import annotations

import re
from typing import Any

_IDEAL_WORD_RANGE = (15, 70)
_WORD_RE = re.compile(r"[a-z0-9']+")


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


class PromptScorer:
    """Heuristic PromptPackage.score - length/redundancy/adherence,
    combined into `overall`. Rule-based, not model-based: there is no
    perceptual or language model in the loop, only word-count and
    substring checks against the PromptPackage itself and the list of
    terms it was supposed to carry (character/object/environment/style
    names). See docs/adr/0013-cinematic-intelligence-layer.md for why
    this is the honest ceiling without a real LLM-as-judge or embedding
    model in this sandbox."""

    def score(self, package: dict[str, Any], *, required_terms: list[str] | None = None) -> dict[str, float]:
        positive_prompt = package["positive_prompt"]
        length_score = self._length_score(positive_prompt)
        redundancy_score = self._redundancy_score(positive_prompt)
        adherence_estimate = self._adherence_score(positive_prompt, required_terms or [])
        overall = round(0.5 * adherence_estimate + 0.25 * length_score + 0.25 * redundancy_score, 4)
        return {
            "adherence_estimate": adherence_estimate,
            "length_score": length_score,
            "redundancy_score": redundancy_score,
            "overall": overall,
        }

    def _length_score(self, positive_prompt: str) -> float:
        word_count = len(positive_prompt.split())
        low, high = _IDEAL_WORD_RANGE
        if low <= word_count <= high:
            return 1.0
        if word_count < low:
            return round(max(word_count / low, 0.0), 4) if low else 0.0
        overage = word_count - high
        return round(max(1.0 - overage / high, 0.0), 4)

    def _redundancy_score(self, positive_prompt: str) -> float:
        words = _tokenize(positive_prompt)
        if not words:
            return 0.0
        unique_ratio = len(set(words)) / len(words)
        return round(unique_ratio, 4)

    def _adherence_score(self, positive_prompt: str, required_terms: list[str]) -> float:
        if not required_terms:
            return 1.0
        haystack = positive_prompt.lower()
        found = sum(1 for term in required_terms if term.lower() in haystack)
        return round(found / len(required_terms), 4)
