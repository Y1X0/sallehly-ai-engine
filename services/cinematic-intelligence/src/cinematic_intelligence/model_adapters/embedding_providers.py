from __future__ import annotations

import math
from urllib.parse import urlparse

from cinematic_intelligence_sdk import IEmbeddingProvider

from .errors import ModelUnavailableError


def _local_path(uri: str) -> str:
    parsed = urlparse(uri)
    return parsed.path if parsed.scheme == "file" else uri


class ClipEmbeddingProvider(IEmbeddingProvider):
    """Real `IEmbeddingProvider` backed by OpenAI CLIP (via `open_clip`),
    the standard model for the perceptual similarity checks
    `IEmbeddingProvider` exists for - it lazily imports `open_clip`/
    `torch`/`PIL` inside `embed_image()`, never at module import time, so
    this class is always importable and registerable even when none of
    those are installed. Requires `pip install open_clip_torch torch
    pillow` plus network access to download `model_name`'s pretrained
    weights (or a local checkpoint) the first time `embed_image()` runs -
    neither is available in this sandbox, so calling it here raises
    `ModelUnavailableError` rather than a bare `ImportError`. See
    `cinematic_intelligence.model_adapters.ModelUnavailableError`.
    """

    def __init__(self, model_name: str = "ViT-B-32", pretrained: str = "openai", device: str = "cpu") -> None:
        self._model_name = model_name
        self._pretrained = pretrained
        self._device = device
        self._model = None
        self._preprocess = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            import open_clip
            import torch
        except ImportError as exc:
            raise ModelUnavailableError(
                "ClipEmbeddingProvider requires 'open_clip_torch' and 'torch' - "
                "install with `pip install open_clip_torch torch` (and a GPU-enabled "
                "torch build for real-time use) to enable real CLIP embeddings."
            ) from exc

        self._torch = torch
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            self._model_name, pretrained=self._pretrained, device=self._device
        )
        self._model.eval()

    def embed_image(self, asset_uri: str) -> tuple[float, ...]:
        self._ensure_loaded()
        try:
            from PIL import Image
        except ImportError as exc:
            raise ModelUnavailableError("ClipEmbeddingProvider requires 'pillow' - install with `pip install pillow`.") from exc

        image = Image.open(_local_path(asset_uri)).convert("RGB")
        tensor = self._preprocess(image).unsqueeze(0).to(self._device)
        with self._torch.no_grad():
            features = self._model.encode_image(tensor)
        return tuple(float(x) for x in features.squeeze(0).tolist())

    def similarity(self, embedding_a: tuple[float, ...], embedding_b: tuple[float, ...]) -> float:
        return _cosine_similarity(embedding_a, embedding_b)


class DinoEmbeddingProvider(IEmbeddingProvider):
    """Real `IEmbeddingProvider` backed by Meta's DINOv2 (via
    `torch.hub`) - the standard model for identity/structural similarity
    (better than CLIP for "is this the same subject/composition" rather
    than "does this match a text description"). Same lazy-import,
    same-honesty posture as `ClipEmbeddingProvider`: requires `pip
    install torch` plus network access to fetch `torch.hub`'s DINOv2
    weights the first time `embed_image()` runs.
    """

    def __init__(self, model_name: str = "dinov2_vits14", device: str = "cpu") -> None:
        self._model_name = model_name
        self._device = device
        self._model = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
        except ImportError as exc:
            raise ModelUnavailableError(
                "DinoEmbeddingProvider requires 'torch' - install with `pip install torch` "
                "(network access is also required the first time, to fetch DINOv2 weights "
                "via torch.hub)."
            ) from exc

        self._torch = torch
        self._model = torch.hub.load("facebookresearch/dinov2", self._model_name)
        self._model.to(self._device).eval()

    def embed_image(self, asset_uri: str) -> tuple[float, ...]:
        self._ensure_loaded()
        try:
            from PIL import Image
            from torchvision import transforms
        except ImportError as exc:
            raise ModelUnavailableError(
                "DinoEmbeddingProvider requires 'pillow' and 'torchvision' - "
                "install with `pip install pillow torchvision`."
            ) from exc

        preprocess = transforms.Compose(
            [
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )
        image = Image.open(_local_path(asset_uri)).convert("RGB")
        tensor = preprocess(image).unsqueeze(0).to(self._device)
        with self._torch.no_grad():
            features = self._model(tensor)
        return tuple(float(x) for x in features.squeeze(0).tolist())

    def similarity(self, embedding_a: tuple[float, ...], embedding_b: tuple[float, ...]) -> float:
        return _cosine_similarity(embedding_a, embedding_b)


def _cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Pure Python, no ML dependency needed - always real and always
    works regardless of which (if any) embedding backend produced
    `a`/`b`, as long as they're equal-length vectors."""
    if len(a) != len(b):
        raise ValueError(f"Embedding length mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))
