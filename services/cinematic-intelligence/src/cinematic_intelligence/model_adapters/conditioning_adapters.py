from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from asset_manager import AssetManager
from cinematic_intelligence_sdk import IReferenceConditioningAdapter, ReferencePackage

from .errors import ModelUnavailableError

_CONTROLNET_SUPPORTED_KINDS = {"character", "object", "environment", "pose"}
_IP_ADAPTER_SUPPORTED_KINDS = {"character", "style"}


def _local_path(uri: str) -> str:
    parsed = urlparse(uri)
    return parsed.path if parsed.scheme == "file" else uri


class ControlNetConditioningAdapter(IReferenceConditioningAdapter):
    """Real `IReferenceConditioningAdapter` that goes beyond a plain
    `conditioning_images` id passthrough: given an `AssetManager` to
    resolve a ReferencePackage's asset ids to real image bytes, its
    `preprocessor="canny"` mode (the default) genuinely runs edge
    detection via Pillow and writes a real preprocessed conditioning
    image - fully functional in this sandbox, no GPU or model weights
    needed (`ImageFilter.FIND_EDGES` is classical image processing, not
    a trained model). `preprocessor="openpose"`/`"depth"` need real
    trained models (`controlnet_aux`) this sandbox doesn't have, and
    raise `ModelUnavailableError` - the same honesty split as
    `ClipEmbeddingProvider` vs. pure-Python cosine similarity.
    """

    def __init__(
        self,
        asset_manager: AssetManager | None = None,
        output_dir: str | Path = "./.docker-data/controlnet-conditioning",
        preprocessor: str = "canny",
    ) -> None:
        self._assets = asset_manager
        self._output_dir = Path(output_dir)
        self._preprocessor = preprocessor

    def supports(self, package: ReferencePackage) -> bool:
        return package.kind in _CONTROLNET_SUPPORTED_KINDS and len(package.images) > 0

    def apply(self, package: ReferencePackage, render_spec: dict[str, Any]) -> dict[str, Any]:
        if not self.supports(package):
            raise ValueError(f"ControlNetConditioningAdapter does not support kind={package.kind!r}")

        primary_image = next((img for img in package.images if img.role in ("primary", "pose")), package.images[0])
        if self._preprocessor == "canny":
            processed_uri = self._run_canny(primary_image.asset_id)
        else:
            processed_uri = self._run_controlnet_aux(primary_image.asset_id)

        conditioning_images = [*render_spec.get("conditioning_images", []), processed_uri]
        return {**render_spec, "conditioning_images": conditioning_images}

    def _run_canny(self, asset_id: str) -> str:
        try:
            from PIL import Image, ImageFilter
        except ImportError as exc:
            raise ModelUnavailableError(
                "ControlNetConditioningAdapter(preprocessor='canny') requires 'pillow' - "
                "install with `pip install pillow`."
            ) from exc

        source_uri = self._resolve_uri(asset_id)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        image = Image.open(_local_path(source_uri)).convert("L")
        edges = image.filter(ImageFilter.FIND_EDGES)
        output_path = self._output_dir / f"{asset_id}_canny.png"
        edges.save(output_path)
        return f"file://{output_path.resolve()}"

    def _run_controlnet_aux(self, asset_id: str) -> str:
        try:
            import controlnet_aux  # noqa: F401
        except ImportError as exc:
            raise ModelUnavailableError(
                f"ControlNetConditioningAdapter(preprocessor={self._preprocessor!r}) requires "
                "'controlnet_aux' plus its real downloaded model weights - install with "
                "`pip install controlnet_aux` (network access required for weights). The "
                "default 'canny' preprocessor only needs pillow and works in this sandbox."
            ) from exc
        raise ModelUnavailableError(  # pragma: no cover - unreachable without controlnet_aux
            f"controlnet_aux is installed but {self._preprocessor!r} model weights were not "
            "found - this preprocessor still needs a real download this sandbox doesn't have."
        )

    def _resolve_uri(self, asset_id: str) -> str:
        if self._assets is None:
            raise ModelUnavailableError(
                "ControlNetConditioningAdapter needs an AssetManager to resolve asset_id -> "
                "real image bytes - construct it with asset_manager=... to enable real "
                "preprocessing."
            )
        record = self._assets.get(asset_id)
        if record is None:
            raise ModelUnavailableError(f"No AssetRecord for asset_id {asset_id!r}")
        return record["versions"][-1]["uri"]


class IPAdapterConditioningAdapter(IReferenceConditioningAdapter):
    """Real `IReferenceConditioningAdapter` backed by IP-Adapter's image
    encoder (`transformers.CLIPVisionModelWithProjection`, the actual
    model IP-Adapter uses to turn a reference image into a conditioning
    embedding) - for injecting a character/style reference's *identity*
    into generation, distinct from ControlNet's *structural* conditioning.
    Unlike ControlNet's canny mode, there is no lightweight classical
    fallback for this - identity conditioning genuinely needs a trained
    vision encoder, so `apply()` always raises `ModelUnavailableError`
    in this sandbox. `supports()` needs no ML dependency and always
    works.
    """

    def supports(self, package: ReferencePackage) -> bool:
        return package.kind in _IP_ADAPTER_SUPPORTED_KINDS and len(package.images) > 0

    def apply(self, package: ReferencePackage, render_spec: dict[str, Any]) -> dict[str, Any]:
        if not self.supports(package):
            raise ValueError(f"IPAdapterConditioningAdapter does not support kind={package.kind!r}")

        try:
            import torch  # noqa: F401
            from transformers import CLIPVisionModelWithProjection  # noqa: F401
        except ImportError as exc:
            raise ModelUnavailableError(
                "IPAdapterConditioningAdapter requires 'transformers' and 'torch' - install "
                "with `pip install transformers torch` plus network access to download the "
                "IP-Adapter image encoder weights the first time apply() runs."
            ) from exc

        primary_image = next((img for img in package.images if img.role == "primary"), package.images[0])  # pragma: no cover
        conditioning_images = [*render_spec.get("conditioning_images", []), primary_image.asset_id]  # pragma: no cover
        return {**render_spec, "conditioning_images": conditioning_images}  # pragma: no cover
