from __future__ import annotations


class ModelUnavailableError(Exception):
    """Raised by any Phase 9 preparation component whose real
    implementation needs a trained model this environment doesn't have
    (a vision-language captioner, a perceptual embedding model, a real
    video-quality metric) - the exact same honesty pattern as
    `cinematic_intelligence.model_adapters.errors.ModelUnavailableError`
    (Phase 7/8), deliberately not imported from there to keep
    `services/training` decoupled from `services/cinematic-intelligence`
    (different domains that happen to need the same kind of gap marker).
    """
