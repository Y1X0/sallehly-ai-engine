from __future__ import annotations

from dataclasses import replace

from cinematic_intelligence_sdk import IPromptTranslator, PromptPackage
from config_sdk import PROMPT_TRANSLATOR_REGISTRY

# Deterministic, illustrative phrasing adjustments per engine - not tuned
# against any engine's real prompt-engineering documentation (this
# sandbox has no access to Wan2.1/Veo/Runway/Luma/Kling/Pika's actual
# APIs). What IS real: the plugin mechanism itself - adding a new engine
# means adding a new IPromptTranslator and registering it, never
# branching inside PromptIntelligenceEngine. See
# docs/adr/0013-cinematic-intelligence-layer.md.
_ENGINE_SUFFIXES: dict[str, str] = {
    "wan2.1": "high quality video, smooth natural motion",
    "veo": "cinematic realism, physically plausible motion",
    "runway": "coherent motion, stable subject identity across frames",
    "luma": "smooth camera motion, dreamlike coherence",
    "kling": "high-fidelity motion consistency",
    "pika": "stylized, expressive motion",
}


def _make_translator(engine_id: str, suffix: str) -> type[IPromptTranslator]:
    class _Translator(IPromptTranslator):
        def translate(self, package: PromptPackage) -> PromptPackage:
            translated = f"{package.positive_prompt}, {suffix}"
            return replace(package, engine_id=engine_id, translated_prompt=translated)

    _Translator.engine_id = engine_id
    _Translator.__name__ = f"{engine_id.replace('.', '').title()}PromptTranslator"
    _Translator.__qualname__ = _Translator.__name__
    return _Translator


Wan21PromptTranslator = _make_translator("wan2.1", _ENGINE_SUFFIXES["wan2.1"])
VeoPromptTranslator = _make_translator("veo", _ENGINE_SUFFIXES["veo"])
RunwayPromptTranslator = _make_translator("runway", _ENGINE_SUFFIXES["runway"])
LumaPromptTranslator = _make_translator("luma", _ENGINE_SUFFIXES["luma"])
KlingPromptTranslator = _make_translator("kling", _ENGINE_SUFFIXES["kling"])
PikaPromptTranslator = _make_translator("pika", _ENGINE_SUFFIXES["pika"])

_BUILTIN_TRANSLATORS = (
    Wan21PromptTranslator,
    VeoPromptTranslator,
    RunwayPromptTranslator,
    LumaPromptTranslator,
    KlingPromptTranslator,
    PikaPromptTranslator,
)


def register_defaults() -> None:
    """Registers every built-in IPromptTranslator into
    PROMPT_TRANSLATOR_REGISTRY, keyed by engine_id. Idempotent - safe to
    call more than once within a process, same pattern as
    post_processing.transitions.register_defaults()."""
    for translator_cls in _BUILTIN_TRANSLATORS:
        PROMPT_TRANSLATOR_REGISTRY.register_if_absent(translator_cls.engine_id, translator_cls)
