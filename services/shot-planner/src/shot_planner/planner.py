from __future__ import annotations

import uuid
from typing import Any

_DEFAULT_SHOT_DURATION_SEC = 3.0
_SHOT_TYPE_ROTATION = ["wide", "medium", "close_up", "medium_close_up"]


class ShotPlanner:
    """Expands a Scene into an ordered list of Shots (bare - shot_type,
    duration, description, transitions; camera/motion/lighting/style are
    filled in afterward by their dedicated Directors, which is why this
    stays a simple heuristic rather than an LLM call: it only needs to
    decide *how many* shots and *how long*, not what's interesting about
    each one).

    Heuristic: split the scene's estimated duration into
    ~_DEFAULT_SHOT_DURATION_SEC-long shots (minimum one shot), rotating
    through a fixed shot-type sequence so a scene doesn't default to a
    single repeated shot type.
    """

    def plan_shots(self, scene: dict[str, Any], estimated_duration_sec: float) -> list[dict[str, Any]]:
        num_shots = max(1, round(estimated_duration_sec / _DEFAULT_SHOT_DURATION_SEC))
        per_shot_duration = estimated_duration_sec / num_shots

        shots = []
        for i in range(num_shots):
            shots.append(
                {
                    "shot_id": f"shot_{uuid.uuid4().hex[:8]}",
                    "order": i,
                    "duration_sec": round(per_shot_duration, 2),
                    "description": f"{scene['summary']} (shot {i + 1} of {num_shots})",
                    "transition_in": "fade_from_black" if i == 0 else "cut",
                    "transition_out": "cut",
                }
            )
            # camera / motion / lighting / style_override are left unset here;
            # populated later by their dedicated Directors (Phase 2).
        return shots

    @staticmethod
    def default_shot_type(order: int) -> str:
        """Convenience for the Camera Director (Phase 2): a sensible
        default shot_type if it needs a starting point before applying
        its own creative logic."""
        return _SHOT_TYPE_ROTATION[order % len(_SHOT_TYPE_ROTATION)]
