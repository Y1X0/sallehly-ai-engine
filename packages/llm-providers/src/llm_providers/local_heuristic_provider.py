from __future__ import annotations

import re
from typing import Any

from .base import ILLMProvider, LLMCapabilities, StructuredGenerationRequest, StructuredGenerationResult
from .errors import ProviderUnavailableError

_GENRE_KEYWORDS = {
    "product": "product commercial",
    "commercial": "product commercial",
    "ad": "product commercial",
    "trailer": "narrative trailer",
    "explainer": "explainer",
    "teaser": "social teaser",
    "music": "music video",
}
_TONE_KEYWORDS = [
    "warm", "premium", "minimalist", "dramatic", "energetic",
    "cinematic", "playful", "elegant", "bold", "calm",
]


class LocalHeuristicLLMProvider(ILLMProvider):
    """Fully offline ILLMProvider: deterministically synthesizes a
    schema-valid CreativeBrief or StoryOutline from the rendered prompt
    text using keyword/regex heuristics - no network call, no API key,
    no real language understanding.

    Exists so the whole system (CreativeDirector through the API layer)
    can run and be tested in this environment without a live Claude
    account - the same "working, fully-offline default for every external
    dependency" pattern as LocalProvider (compute) and FakeLLMProvider
    (scripted unit tests). This one instead answers *arbitrary* requests,
    which is what a running API server needs. Never use in production -
    it does not understand the brief, it pattern-matches it.
    """

    provider_id = "local-heuristic"

    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(
            provider_id=self.provider_id,
            model_id="local-heuristic-1",
            supports_structured_output=True,
            supports_vision=False,
            max_context_tokens=8_000,
        )

    def generate_structured(self, request: StructuredGenerationRequest) -> StructuredGenerationResult:
        title = request.output_schema.get("title", "")
        if title == "CreativeBrief":
            output = self._creative_brief(request.user_prompt)
        elif title == "StoryOutline":
            output = self._story_outline(request.user_prompt)
        else:
            raise ProviderUnavailableError(
                f"LocalHeuristicLLMProvider has no stub for schema {title!r} - "
                "it only understands CreativeBrief and StoryOutline requests."
            )
        return StructuredGenerationResult(
            output=output, provider_id=self.provider_id, model_id="local-heuristic-1"
        )

    def _creative_brief(self, prompt: str) -> dict[str, Any]:
        raw_idea = self._extract(prompt, r"Raw idea:\s*(.+)") or prompt.strip()
        lowered = raw_idea.lower()

        genre = next((v for k, v in _GENRE_KEYWORDS.items() if k in lowered), "general video")
        tone_keywords = [word for word in _TONE_KEYWORDS if word in lowered] or ["cinematic"]

        return {
            "genre": genre,
            "tone_keywords": tone_keywords,
            "target_audience": "general audience",
            "key_message": raw_idea[:140],
            "must_include": [],
            "must_avoid": [],
            "inferred_target_duration_sec": None,
            "inferred_aspect_ratio": None,
            "ambiguities": [
                "LocalHeuristicLLMProvider used a keyword heuristic, not real language understanding."
            ],
        }

    def _story_outline(self, prompt: str) -> dict[str, Any]:
        duration = float(self._extract(prompt, r"target_duration_sec:\s*([\d.]+)") or 15.0)
        genre = self._extract(prompt, r"genre:\s*(.+)") or "general video"
        raw_idea = self._extract(prompt, r"raw_idea:\s*(.+)") or "An idea."

        scene_specs = [
            ("hook", "Opening hook establishing the subject.", 0.3),
            ("build", "Development of the core idea/product/story.", 0.5),
            ("resolution", "Closing beat / brand or story resolution.", 0.2),
        ]
        scene_skeleton = []
        narrative_arc = []
        for i, (role, summary, fraction) in enumerate(scene_specs):
            scene_skeleton.append(
                {
                    "order": i,
                    "role": role,
                    "summary": f"{summary} ({genre})",
                    "location": "unspecified",
                    "estimated_duration_sec": round(duration * fraction, 1),
                }
            )
            narrative_arc.append(
                {
                    "beat_id": f"beat_{i + 1}",
                    "order": i,
                    "purpose": role if role in ("hook", "resolution") else "build",
                    "description": summary,
                }
            )

        # Rounding can leave the total slightly off target_duration_sec;
        # correct the last scene so downstream duration-budget checks hold.
        total = sum(scene["estimated_duration_sec"] for scene in scene_skeleton)
        scene_skeleton[-1]["estimated_duration_sec"] = round(
            scene_skeleton[-1]["estimated_duration_sec"] + (duration - total), 1
        )

        return {
            "logline": raw_idea[:160],
            "narrative_arc": narrative_arc,
            "scene_skeleton": scene_skeleton,
            "continuity_anchors": {"characters": [], "locations": []},
            "global_style_hint": genre,
        }

    @staticmethod
    def _extract(text: str, pattern: str) -> str | None:
        match = re.search(pattern, text)
        return match.group(1).strip() if match else None
