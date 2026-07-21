from __future__ import annotations

from video_composition_sdk import ITransitionPlugin, Transition, TransitionRecipe

_DEFAULT_XFADE_DURATION_SEC = 0.5


class CinematicCutPlugin(ITransitionPlugin):
    """A hard cut - no overlap, no filter. The default when a shot's
    transition is "cut" (services/shot-planner's default for every shot
    but the first)."""

    plugin_id = "cinematic_cut"

    def resolve(self, transition: Transition) -> TransitionRecipe:
        return TransitionRecipe(mode="hard_cut")


class FadeInPlugin(ITransitionPlugin):
    """Fades the whole sequence in from black - a single-clip effect at
    the very start, not a crossfade between two clips (see
    FfmpegCompositor). Maps from shot.schema.json's "fade_from_black"."""

    plugin_id = "fade_in"

    def resolve(self, transition: Transition) -> TransitionRecipe:
        return TransitionRecipe(mode="fade_from_black", duration_sec=transition.duration_sec or 0.6)


class FadeOutPlugin(ITransitionPlugin):
    """Fades the whole sequence out to black - a single-clip effect at
    the very end. Maps from shot.schema.json's "fade_to_black"."""

    plugin_id = "fade_out"

    def resolve(self, transition: Transition) -> TransitionRecipe:
        return TransitionRecipe(mode="fade_to_black", duration_sec=transition.duration_sec or 0.6)


class DissolvePlugin(ITransitionPlugin):
    """Classic crossfade - ffmpeg xfade's "dissolve" preset."""

    plugin_id = "dissolve"

    def resolve(self, transition: Transition) -> TransitionRecipe:
        return TransitionRecipe(
            mode="xfade",
            xfade_transition="dissolve",
            duration_sec=transition.duration_sec or _DEFAULT_XFADE_DURATION_SEC,
        )


class MatchCutPlugin(ITransitionPlugin):
    """Approximates a match cut (a cut on matching action/composition
    between two shots) as a very quick plain fade. A true match cut
    needs shot-specific visual alignment decided upstream (the Camera
    Director choosing matching framing across the two shots) - this
    plugin cannot invent that alignment, so it deliberately keeps the
    overlap short enough (default 0.15s) that it reads as a cut rather
    than a dissolve, honoring the *intent* without overclaiming a
    content-aware match."""

    plugin_id = "match_cut"

    def resolve(self, transition: Transition) -> TransitionRecipe:
        return TransitionRecipe(mode="xfade", xfade_transition="fade", duration_sec=transition.duration_sec or 0.15)


class WipePlugin(ITransitionPlugin):
    """A directional wipe - ffmpeg xfade's "wipeleft" by default;
    transition.params={"direction": "left"|"right"|"up"|"down"} selects
    the matching wipe*/wipe{t,b}{l,r} preset."""

    plugin_id = "wipe"

    _DIRECTION_TO_XFADE = {
        "left": "wipeleft",
        "right": "wiperight",
        "up": "wipeup",
        "down": "wipedown",
    }

    def resolve(self, transition: Transition) -> TransitionRecipe:
        direction = transition.params.get("direction", "left")
        xfade_name = self._DIRECTION_TO_XFADE.get(direction, "wipeleft")
        return TransitionRecipe(
            mode="xfade", xfade_transition=xfade_name, duration_sec=transition.duration_sec or _DEFAULT_XFADE_DURATION_SEC
        )


class WhipPanPlugin(ITransitionPlugin):
    """Approximates a whip pan (a fast, motion-blurred camera swing
    connecting two shots) using ffmpeg xfade's "hblur" preset, which
    produces the horizontal motion-blur look a whip pan reads as. Not a
    literal simulated camera pan (that would need per-shot camera
    motion vectors from the Camera Director) - documented as an
    approximation, same honesty as MatchCutPlugin."""

    plugin_id = "whip_pan"

    def resolve(self, transition: Transition) -> TransitionRecipe:
        return TransitionRecipe(
            mode="xfade", xfade_transition="hblur", duration_sec=transition.duration_sec or 0.3
        )


class ZoomPlugin(ITransitionPlugin):
    """A zoom transition - ffmpeg xfade's "zoomin" preset."""

    plugin_id = "zoom"

    def resolve(self, transition: Transition) -> TransitionRecipe:
        return TransitionRecipe(
            mode="xfade", xfade_transition="zoomin", duration_sec=transition.duration_sec or _DEFAULT_XFADE_DURATION_SEC
        )
