"""Phase 8 model adapters (services/cinematic-intelligence/.../
model_adapters): ClipEmbeddingProvider/DinoEmbeddingProvider
(IEmbeddingProvider) and ControlNetConditioningAdapter/
IPAdapterConditioningAdapter (IReferenceConditioningAdapter).

None of torch/open_clip/torchvision/controlnet_aux/transformers are
installed in this sandbox (confirmed: `import torch` etc. all raise
ImportError) - by design (ADR 0014), every adapter method that would
need one of them raises a clear ModelUnavailableError instead of
crashing on a bare ImportError or silently faking a result. What *is*
real and tested for real here: cosine similarity (pure Python), the
structural `supports()` checks (no ML dependency), and
ControlNetConditioningAdapter's canny-edge-detection path, which
genuinely only needs Pillow (already a hard dependency of this
package) and needs no GPU or downloaded weights.
"""

from __future__ import annotations

import importlib.util
import math

import pytest
from asset_manager import AssetManager
from cinematic_intelligence.model_adapters import (
    ClipEmbeddingProvider,
    ControlNetConditioningAdapter,
    DinoEmbeddingProvider,
    IPAdapterConditioningAdapter,
    ModelUnavailableError,
    register_defaults,
)
from cinematic_intelligence_sdk import ReferenceImageEntry, ReferencePackage
from config_sdk import CONDITIONING_ADAPTER_REGISTRY, EMBEDDING_PROVIDER_REGISTRY
from PIL import Image


# services/training's optional `gpu-training` extra (docs/adr/0024-wan22-real-training-backend.md)
# adds torch/transformers to this uv workspace's single shared virtualenv
# - when that extra is installed, torch/transformers become importable
# from *any* package's code, including this one, invalidating the two
# tests below (which assert ModelUnavailableError specifically because
# torch/transformers are absent). Skip them in that specific
# environment rather than asserting a precondition that may no longer
# hold; every other test in this file has no such dependency and is
# unaffected either way.
_TORCH_INSTALLED = importlib.util.find_spec("torch") is not None
_TRANSFORMERS_INSTALLED = importlib.util.find_spec("transformers") is not None


def _reference_package(kind: str, asset_id: str, project_id: str = "proj_model_adapters") -> ReferencePackage:
    return ReferencePackage(
        schema_version="1.0",
        package_id="pkg_1",
        project_id=project_id,
        kind=kind,
        images=(ReferenceImageEntry(asset_id=asset_id, role="primary"),),
    )


class TestEmbeddingProviderSimilarity:
    """Pure math, zero ML dependency - always real regardless of what's
    installed."""

    @pytest.mark.parametrize("provider_cls", [ClipEmbeddingProvider, DinoEmbeddingProvider])
    def test_identical_vectors_have_similarity_one(self, provider_cls):
        provider = provider_cls()
        vector = (1.0, 2.0, 3.0)
        assert provider.similarity(vector, vector) == pytest.approx(1.0)

    @pytest.mark.parametrize("provider_cls", [ClipEmbeddingProvider, DinoEmbeddingProvider])
    def test_orthogonal_vectors_have_similarity_zero(self, provider_cls):
        provider = provider_cls()
        assert provider.similarity((1.0, 0.0), (0.0, 1.0)) == pytest.approx(0.0)

    @pytest.mark.parametrize("provider_cls", [ClipEmbeddingProvider, DinoEmbeddingProvider])
    def test_opposite_vectors_clamp_to_zero_not_negative(self, provider_cls):
        provider = provider_cls()
        assert provider.similarity((1.0, 0.0), (-1.0, 0.0)) == pytest.approx(0.0)

    def test_zero_vector_is_similarity_zero_not_a_crash(self):
        provider = ClipEmbeddingProvider()
        assert provider.similarity((0.0, 0.0), (1.0, 1.0)) == 0.0

    def test_mismatched_lengths_raise_value_error(self):
        provider = ClipEmbeddingProvider()
        with pytest.raises(ValueError, match="length mismatch"):
            provider.similarity((1.0, 2.0), (1.0,))

    def test_known_angle_matches_hand_computed_cosine(self):
        # cos(45 deg) between (1, 0) and (1, 1)/sqrt(2)
        provider = DinoEmbeddingProvider()
        result = provider.similarity((1.0, 0.0), (1.0, 1.0))
        assert result == pytest.approx(1 / math.sqrt(2), abs=1e-9)


class TestEmbeddingProviderEmbedImageUnavailable:
    """embed_image() genuinely needs torch/open_clip/torchvision -
    absent in this sandbox - so it must raise ModelUnavailableError, not
    ImportError, not a fabricated embedding."""

    def test_clip_embed_image_raises_model_unavailable(self):
        provider = ClipEmbeddingProvider()
        with pytest.raises(ModelUnavailableError, match="open_clip_torch"):
            provider.embed_image("file:///tmp/does-not-matter.png")

    @pytest.mark.skipif(_TORCH_INSTALLED, reason="torch is installed (gpu-training extra) - see module comment")
    def test_dino_embed_image_raises_model_unavailable(self):
        provider = DinoEmbeddingProvider()
        with pytest.raises(ModelUnavailableError, match="torch"):
            provider.embed_image("file:///tmp/does-not-matter.png")


class TestControlNetSupports:
    @pytest.mark.parametrize("kind", ["character", "object", "environment", "pose"])
    def test_supports_recognized_kinds_with_images(self, kind):
        adapter = ControlNetConditioningAdapter()
        assert adapter.supports(_reference_package(kind, "asset_1")) is True

    def test_does_not_support_style(self):
        adapter = ControlNetConditioningAdapter()
        assert adapter.supports(_reference_package("style", "asset_1")) is False

    def test_does_not_support_package_with_no_images(self):
        adapter = ControlNetConditioningAdapter()
        package = ReferencePackage(
            schema_version="1.0", package_id="pkg_2", project_id="proj_x", kind="character", images=()
        )
        assert adapter.supports(package) is False


class TestControlNetCannyRealPreprocessing:
    """The one genuinely-functional-in-this-sandbox model adapter path:
    real Pillow edge detection, no GPU or downloaded weights needed."""

    def _register_test_image(self, tmp_path, asset_manager: AssetManager) -> str:
        image_path = tmp_path / "source.png"
        image = Image.new("RGB", (64, 64), color="black")
        for x in range(20, 44):
            for y in range(20, 44):
                image.putpixel((x, y), (255, 255, 255))
        image.save(image_path)
        record = asset_manager.register("proj_canny", kind="image", uri=str(image_path))
        return record["asset_id"]

    def test_apply_produces_a_real_preprocessed_conditioning_image(self, tmp_path):
        asset_manager = AssetManager()
        asset_id = self._register_test_image(tmp_path, asset_manager)
        adapter = ControlNetConditioningAdapter(asset_manager=asset_manager, output_dir=tmp_path / "out")
        package = _reference_package("character", asset_id, project_id="proj_canny")

        result = adapter.apply(package, {"conditioning_images": ["existing_ref"]})

        assert result["conditioning_images"][0] == "existing_ref"
        new_uri = result["conditioning_images"][1]
        assert new_uri.startswith("file://")
        output_path = new_uri.removeprefix("file://")

        # Prove it's a real, valid image file - not a placeholder - and
        # that edge detection actually ran (a white square on a black
        # background has edges, i.e. non-uniform pixel values).
        edges = Image.open(output_path)
        pixels = list(edges.getdata())
        assert len(set(pixels)) > 1

    def test_apply_with_unsupported_kind_raises_value_error(self):
        adapter = ControlNetConditioningAdapter()
        package = _reference_package("style", "asset_1")
        with pytest.raises(ValueError, match="does not support"):
            adapter.apply(package, {})

    def test_apply_without_asset_manager_raises_model_unavailable(self):
        adapter = ControlNetConditioningAdapter()  # no asset_manager
        package = _reference_package("character", "asset_1")
        with pytest.raises(ModelUnavailableError, match="AssetManager"):
            adapter.apply(package, {})

    def test_apply_with_unknown_asset_id_raises_model_unavailable(self):
        asset_manager = AssetManager()
        adapter = ControlNetConditioningAdapter(asset_manager=asset_manager)
        package = _reference_package("character", "does-not-exist")
        with pytest.raises(ModelUnavailableError, match="No AssetRecord"):
            adapter.apply(package, {})

    def test_openpose_preprocessor_raises_model_unavailable(self, tmp_path):
        asset_manager = AssetManager()
        asset_id = self._register_test_image(tmp_path, asset_manager)
        adapter = ControlNetConditioningAdapter(asset_manager=asset_manager, preprocessor="openpose")
        package = _reference_package("pose", asset_id, project_id="proj_canny")

        with pytest.raises(ModelUnavailableError, match="controlnet_aux"):
            adapter.apply(package, {})


class TestIPAdapterSupports:
    @pytest.mark.parametrize("kind", ["character", "style"])
    def test_supports_recognized_kinds_with_images(self, kind):
        adapter = IPAdapterConditioningAdapter()
        assert adapter.supports(_reference_package(kind, "asset_1")) is True

    def test_does_not_support_object(self):
        adapter = IPAdapterConditioningAdapter()
        assert adapter.supports(_reference_package("object", "asset_1")) is False

    @pytest.mark.skipif(
        _TRANSFORMERS_INSTALLED, reason="transformers is installed (gpu-training extra) - see module comment"
    )
    def test_apply_raises_model_unavailable(self):
        adapter = IPAdapterConditioningAdapter()
        package = _reference_package("character", "asset_1")
        with pytest.raises(ModelUnavailableError, match="transformers"):
            adapter.apply(package, {})

    def test_apply_with_unsupported_kind_raises_value_error_before_any_import(self):
        adapter = IPAdapterConditioningAdapter()
        package = _reference_package("object", "asset_1")
        with pytest.raises(ValueError, match="does not support"):
            adapter.apply(package, {})


class TestRegisterDefaults:
    def test_register_defaults_populates_both_registries_and_is_idempotent(self):
        register_defaults()
        register_defaults()  # must not raise on a second call

        assert "clip" in EMBEDDING_PROVIDER_REGISTRY
        assert "dino" in EMBEDDING_PROVIDER_REGISTRY
        assert "controlnet" in CONDITIONING_ADAPTER_REGISTRY
        assert "ip_adapter" in CONDITIONING_ADAPTER_REGISTRY

        assert isinstance(EMBEDDING_PROVIDER_REGISTRY.create("clip"), ClipEmbeddingProvider)
        assert isinstance(CONDITIONING_ADAPTER_REGISTRY.create("controlnet"), ControlNetConditioningAdapter)
