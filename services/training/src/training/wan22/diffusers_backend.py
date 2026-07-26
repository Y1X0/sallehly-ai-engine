from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import ModelUnavailableError
from ..lora import LoRAConfig
from .backend import IWan22TrainingBackend, TrainStepResult
from .dataset_adapter import Wan22ManifestEntry
from .lora_config import EXPERT_HIGH_NOISE, EXPERT_LOW_NOISE, EXPERT_UNIFIED, expected_experts

try:
    import torch
except ImportError:  # pragma: no cover - exercised via ModelUnavailableError below
    torch = None  # type: ignore[assignment]

_MISSING_DEPS_MESSAGE = (
    "training[gpu-training] extra is not installed - torch/diffusers/peft are required for "
    "Wan22DiffusersBackend. Install with `uv sync --all-packages --extra gpu-training` or "
    "`pip install \"training[gpu-training]\"`. See docs/adr/0024-wan22-real-training-backend.md."
)

# Real Wan2.2 VAE/transformer constants (diffusers.AutoencoderKLWan defaults,
# verified against diffusers==0.39.0's actual class signatures - see
# docs/adr/0024-wan22-real-training-backend.md for how these were checked).
_VAE_SPATIAL_SCALE = 8
_VAE_TEMPORAL_SCALE = 4
_LATENT_CHANNELS = 16
_TEXT_DIM = 4096
_TEXT_SEQ_LEN = 512

# A tiny-but-real WanTransformer3DModel config: same class, same forward()
# contract, same peft LoRA target modules as a real Wan2.2 transformer -
# just ~20K params instead of 5B/14B, so it trains on CPU in well under a
# second. Verified end-to-end (forward, backward, optimizer step,
# peft save_pretrained) before being committed here - not a guess at
# whether the mechanism works.
_SMOKE_TEST_TRANSFORMER_KWARGS: dict[str, Any] = {
    "patch_size": (1, 2, 2),
    "num_attention_heads": 2,
    "attention_head_dim": 16,
    "in_channels": 4,
    "out_channels": 4,
    "text_dim": 32,
    "freq_dim": 16,
    "ffn_dim": 32,
    "num_layers": 1,
    "cross_attn_norm": True,
    "qk_norm": "rms_norm_across_heads",
    "rope_max_seq_len": 32,
}
_SMOKE_TEST_LATENT_CHANNELS = 4
_SMOKE_TEST_TEXT_DIM = 32
_SMOKE_TEST_TEXT_SEQ_LEN = 8


@dataclass(frozen=True)
class Wan22ModelSource:
    """Where one expert's real Wan2.2 transformer weights come from - an
    HF Hub repo id (e.g. "Wan-AI/Wan2.2-T2V-A14B-Diffusers") or a local
    directory already populated by `training.hf_download`
    (`resolve_local_weights()`), plus which subfolder inside it holds
    this expert's transformer.

    `subfolder` mirrors the real Wan-AI Diffusers-format repo layout,
    confirmed against `diffusers.WanPipeline.__init__`'s actual
    `transformer`/`transformer_2` parameters (diffusers==0.39.0):
    `"transformer"` is the sole network for a unified (TI2V-5B) model or
    the high-noise expert of an A14B MoE model; `"transformer_2"` is the
    A14B's low-noise expert. Re-verify this convention against the
    specific HF repo you point at before a real run - this was checked
    against the installed diffusers version's pipeline signature, not
    against every possible community re-upload's folder layout.
    """

    pretrained_model_name_or_path: str
    subfolder: str = "transformer"
    revision: str | None = None


def default_model_sources(base_model_id: str, pretrained_model_name_or_path: str) -> dict[str, Wan22ModelSource]:
    """Builds the `{expert_name: Wan22ModelSource}` mapping `expected_experts()`
    requires, for the common case where every expert lives in one HF
    repo under the standard `transformer`/`transformer_2` subfolders."""
    experts = expected_experts(base_model_id)
    if experts == frozenset({EXPERT_UNIFIED}):
        return {EXPERT_UNIFIED: Wan22ModelSource(pretrained_model_name_or_path, subfolder="transformer")}
    return {
        EXPERT_HIGH_NOISE: Wan22ModelSource(pretrained_model_name_or_path, subfolder="transformer"),
        EXPERT_LOW_NOISE: Wan22ModelSource(pretrained_model_name_or_path, subfolder="transformer_2"),
    }


class Wan22BatchEncoder(ABC):
    """Produces the `(hidden_states, encoder_hidden_states)` tensor pair
    `WanTransformer3DModel.forward()` requires from one
    `Wan22ManifestEntry`. Kept separate from `Wan22DiffusersBackend`
    itself (same "the expensive/uncertain part is swappable" shape as
    `ICaptionProvider`/`IDuplicateDetector` in `training.dataset`)
    because encoding real video+caption bytes requires real downloaded
    Wan2.2 weights (a VAE + text encoder) while the transformer
    forward/backward/optimizer mechanism this backend exists to prove
    does not."""

    @abstractmethod
    def encode(self, entry: Wan22ManifestEntry, *, device: str) -> tuple[Any, Any]: ...


class RandomLatentBatchEncoder(Wan22BatchEncoder):
    """Deterministic, seeded synthetic `hidden_states`/`encoder_hidden_states`
    - shaped from the manifest entry's REAL metadata (real
    width/height/num_frames run through Wan2.2's real VAE
    spatial/temporal downsample factors) but filled with random values
    rather than a real VAE/text-encoder pass. This is the "prove the
    training mechanism without the expensive resource" default - the
    same posture `DryRunTrainer`/`LocalProvider`/`HeuristicCaptionProvider`
    already take elsewhere in this codebase - used until real Wan2.2
    weights are downloaded (`training.hf_download`) and a real
    `DiffusersBatchEncoder` is constructed and passed in instead. Every
    forward/backward/optimizer step downstream of this encoder is fully
    real; only the *input* is synthetic.
    """

    def __init__(
        self,
        *,
        seed: int = 0,
        latent_channels: int = _LATENT_CHANNELS,
        text_dim: int = _TEXT_DIM,
        text_seq_len: int = _TEXT_SEQ_LEN,
    ) -> None:
        if torch is None:
            raise ModelUnavailableError(_MISSING_DEPS_MESSAGE)
        self._seed = seed
        self._latent_channels = latent_channels
        self._text_dim = text_dim
        self._text_seq_len = text_seq_len

    def encode(self, entry: Wan22ManifestEntry, *, device: str) -> tuple[Any, Any]:
        latent_frames = max(1, (entry.num_frames - 1) // _VAE_TEMPORAL_SCALE + 1)
        latent_h = max(1, entry.height // _VAE_SPATIAL_SCALE)
        latent_w = max(1, entry.width // _VAE_SPATIAL_SCALE)
        clip_seed = (self._seed + hash(entry.clip_id)) & 0xFFFFFFFF
        generator = torch.Generator(device="cpu").manual_seed(clip_seed)

        hidden_states = torch.randn(
            1, self._latent_channels, latent_frames, latent_h, latent_w, generator=generator
        ).to(device)
        encoder_hidden_states = torch.randn(1, self._text_seq_len, self._text_dim, generator=generator).to(device)
        return hidden_states, encoder_hidden_states


class DiffusersBatchEncoder(Wan22BatchEncoder):
    """Real video decode (`imageio`) -> real `AutoencoderKLWan` encode
    (normalized via the VAE's own `latents_mean`/`latents_std` config,
    read off the loaded model, not hardcoded here) and real
    `UMT5EncoderModel` text encode. This is the encoder half of the
    training step once real Wan2.2 weights (`training.hf_download`) and
    a real dataset (real video bytes at each manifest entry's
    `video_path`) are both available.

    Not exercised against a real Wan2.2 checkpoint or real video in this
    sandbox (no GPU, no multi-GB weights, no sample footage available
    here) - the VAE mean/std normalization and tokenizer call shape are
    written to match the installed diffusers version's documented
    conventions, but this should be run against one real clip and
    visually/numerically sanity-checked before being trusted for an
    actual training run. See docs/EXECUTION_PLAN_FIRST_GPU_RUN.md.
    """

    def __init__(self, *, vae: Any, tokenizer: Any, text_encoder: Any) -> None:
        if torch is None:
            raise ModelUnavailableError(_MISSING_DEPS_MESSAGE)
        self._vae = vae
        self._tokenizer = tokenizer
        self._text_encoder = text_encoder

    def encode(self, entry: Wan22ManifestEntry, *, device: str) -> tuple[Any, Any]:
        try:
            import imageio.v3 as iio
        except ImportError as exc:
            raise ModelUnavailableError(_MISSING_DEPS_MESSAGE) from exc

        raw_frames = iio.imread(entry.video_path)[: entry.num_frames]
        frames = torch.from_numpy(raw_frames.copy()).float() / 127.5 - 1.0  # (F, H, W, C), range [-1, 1]
        video = frames.permute(3, 0, 1, 2).unsqueeze(0).to(device)  # (1, C, F, H, W)

        with torch.no_grad():
            latents = self._vae.encode(video).latent_dist.sample()
            mean = torch.tensor(self._vae.config.latents_mean, device=device).view(1, -1, 1, 1, 1)
            std = torch.tensor(self._vae.config.latents_std, device=device).view(1, -1, 1, 1, 1)
            latents = (latents - mean) / std

            tokens = self._tokenizer(
                entry.caption, padding="max_length", max_length=_TEXT_SEQ_LEN, truncation=True, return_tensors="pt"
            ).to(device)
            encoder_hidden_states = self._text_encoder(**tokens).last_hidden_state

        return latents, encoder_hidden_states


class Wan22DiffusersBackend(IWan22TrainingBackend):
    """The real `IWan22TrainingBackend` implementation: loads a real
    `diffusers.WanTransformer3DModel` per expert (either real Wan2.2
    weights via `model_sources`, or a tiny randomly-initialized instance
    of the same class for `smoke_test=True`), wraps it with a real
    `peft` LoRA adapter matching this run's `LoRAConfig`, and runs a
    real forward pass, a real rectified-flow loss, a real backward pass,
    and a real `AdamW` optimizer step on every `train_step()` call.
    `save_checkpoint()` writes the LoRA adapter only (`peft`'s own
    `save_pretrained`, i.e. `adapter_model.safetensors` +
    `adapter_config.json` - megabytes, not the multi-GB base model)
    under `output_dir`.

    This mechanism - tiny `WanTransformer3DModel` + `peft.get_peft_model`
    + forward/backward/`AdamW.step()`/`save_pretrained` - was verified
    end-to-end against the installed diffusers/peft versions before this
    class was written (see docs/adr/0024-wan22-real-training-backend.md);
    it is not a guess at whether `peft` supports this architecture.

    What is NOT independently verified here: the flow-matching loss
    formulation's exact match to Wan2.2's own published training recipe
    (this uses the standard rectified-flow `target = noise - sample`
    velocity objective diffusers' own Flux/SD3/Wan training scripts use,
    not a byte-for-byte reimplementation of `FlowMatchEulerDiscreteScheduler`'s
    internals), and `DiffusersBatchEncoder`'s VAE/text-encoder shapes
    against real weights (no GPU or real weights exist in this sandbox
    to test that against). Both are real, complete code, not stubs -
    but should be checked against a real short run before being trusted
    for a production training job.
    """

    def __init__(
        self,
        *,
        base_model_id: str,
        model_sources: dict[str, Wan22ModelSource] | None = None,
        smoke_test: bool = False,
        batch_encoder: Wan22BatchEncoder | None = None,
        device: str = "cpu",
        learning_rate: float = 1e-4,
        seed: int = 0,
        num_train_timesteps: int = 1000,
    ) -> None:
        if torch is None:
            raise ModelUnavailableError(_MISSING_DEPS_MESSAGE)
        if smoke_test and model_sources:
            raise ValueError("Wan22DiffusersBackend: pass either smoke_test=True or model_sources, not both")
        if not smoke_test and not model_sources:
            raise ValueError("Wan22DiffusersBackend: model_sources is required unless smoke_test=True")

        self._base_model_id = base_model_id
        self._model_sources = dict(model_sources or {})
        self._smoke_test = smoke_test
        self._device = device
        self._learning_rate = learning_rate
        self._num_train_timesteps = num_train_timesteps
        self._batch_encoder = batch_encoder or (
            RandomLatentBatchEncoder(
                seed=seed,
                latent_channels=_SMOKE_TEST_LATENT_CHANNELS,
                text_dim=_SMOKE_TEST_TEXT_DIM,
                text_seq_len=_SMOKE_TEST_TEXT_SEQ_LEN,
            )
            if smoke_test
            else RandomLatentBatchEncoder(seed=seed)
        )

        self._base_models: dict[str, Any] = {}
        self._peft_models: dict[str, Any] = {}
        self._optimizers: dict[str, Any] = {}
        self._applied_lora: dict[str, LoRAConfig] = {}

    def _load_base_model(self, expert: str) -> Any:
        if expert in self._base_models:
            return self._base_models[expert]

        try:
            from diffusers import WanTransformer3DModel
        except ImportError as exc:
            raise ModelUnavailableError(_MISSING_DEPS_MESSAGE) from exc

        if self._smoke_test:
            model = WanTransformer3DModel(**_SMOKE_TEST_TRANSFORMER_KWARGS)
        else:
            source = self._model_sources.get(expert)
            if source is None:
                raise ModelUnavailableError(
                    f"No Wan22ModelSource configured for expert={expert!r} - cannot load real weights. "
                    f"Configured experts: {sorted(self._model_sources)}. Run "
                    "training.hf_download to fetch weights first - see "
                    "docs/EXECUTION_PLAN_FIRST_GPU_RUN.md."
                )
            model = WanTransformer3DModel.from_pretrained(
                source.pretrained_model_name_or_path,
                subfolder=source.subfolder,
                revision=source.revision,
            )

        model = model.to(self._device)
        self._base_models[expert] = model
        return model

    def _get_trainable(self, expert: str, lora_config: LoRAConfig) -> tuple[Any, Any]:
        if expert in self._peft_models:
            if self._applied_lora[expert] != lora_config:
                raise ValueError(
                    f"Wan22DiffusersBackend already applied a different LoRAConfig to expert={expert!r} "
                    "earlier in this run - the LoRA configuration cannot change mid-run"
                )
            return self._peft_models[expert], self._optimizers[expert]

        try:
            from peft import LoraConfig as PeftLoraConfig
            from peft import get_peft_model
        except ImportError as exc:
            raise ModelUnavailableError(_MISSING_DEPS_MESSAGE) from exc

        base_model = self._load_base_model(expert)
        peft_config = PeftLoraConfig(
            r=lora_config.rank,
            lora_alpha=lora_config.alpha,
            target_modules=list(lora_config.target_modules),
            lora_dropout=lora_config.dropout,
        )
        peft_model = get_peft_model(base_model, peft_config)
        trainable_params = [p for p in peft_model.parameters() if p.requires_grad]
        if not trainable_params:
            raise ValueError(
                f"LoRAConfig.target_modules={list(lora_config.target_modules)!r} matched no modules on "
                f"expert={expert!r}'s WanTransformer3DModel - no parameters would be trained"
            )
        optimizer = torch.optim.AdamW(trainable_params, lr=self._learning_rate)

        self._peft_models[expert] = peft_model
        self._optimizers[expert] = optimizer
        self._applied_lora[expert] = lora_config
        return peft_model, optimizer

    def train_step(
        self, *, expert: str, step: int, batch: Wan22ManifestEntry, lora_config: LoRAConfig
    ) -> TrainStepResult:
        peft_model, optimizer = self._get_trainable(expert, lora_config)
        peft_model.train()

        hidden_states, encoder_hidden_states = self._batch_encoder.encode(batch, device=self._device)
        noise = torch.randn_like(hidden_states)

        # Rectified-flow / flow-matching training objective: sample a
        # random timestep fraction sigma in [0, 1), linearly interpolate
        # between the clean sample and noise at that point, and train the
        # model to predict the velocity (noise - sample) - the same
        # objective diffusers' own FlowMatchEulerDiscreteScheduler-based
        # training scripts (Flux/SD3/Wan) use. See this class's own
        # docstring for what has and has not been verified about this
        # choice.
        batch_size = hidden_states.shape[0]
        timesteps = torch.randint(0, self._num_train_timesteps, (batch_size,), device=self._device, dtype=torch.long)
        sigmas = (timesteps.float() / float(self._num_train_timesteps)).view(-1, 1, 1, 1, 1)
        noisy_hidden_states = (1.0 - sigmas) * hidden_states + sigmas * noise
        target = noise - hidden_states

        model_pred = peft_model(
            hidden_states=noisy_hidden_states,
            timestep=timesteps,
            encoder_hidden_states=encoder_hidden_states,
            return_dict=False,
        )
        if isinstance(model_pred, tuple):
            model_pred = model_pred[0]

        loss = torch.nn.functional.mse_loss(model_pred.float(), target.float())

        optimizer.zero_grad()
        loss.backward()
        trainable_params = [p for p in peft_model.parameters() if p.requires_grad]
        grad_norm = torch.nn.utils.clip_grad_norm_(trainable_params, max_norm=1.0e9)
        optimizer.step()

        return TrainStepResult(
            loss=float(loss.detach().cpu().item()),
            metrics={"grad_norm": float(grad_norm.detach().cpu().item())},
        )

    def save_checkpoint(self, *, expert: str, step: int, output_dir: Path) -> str:
        if expert not in self._peft_models:
            raise ModelUnavailableError(
                f"save_checkpoint called for expert={expert!r} before any train_step ran for it"
            )
        target_dir = Path(output_dir) / "adapters" / expert / f"step_{step:06d}"
        target_dir.mkdir(parents=True, exist_ok=True)
        self._peft_models[expert].save_pretrained(str(target_dir))
        return f"file://{target_dir.resolve()}"


def build_smoke_test_backend(
    *, base_model_id: str, learning_rate: float = 1e-4, seed: int = 0
) -> Wan22DiffusersBackend:
    """The controlled, zero-cost smoke test required before any real GPU
    run: real `WanTransformer3DModel` + real `peft` LoRA injection +
    real forward/backward/optimizer/checkpoint-save, at a tiny
    randomly-initialized scale (tens of thousands of parameters, not
    Wan2.2's real 5B/14B) so it completes on CPU in well under a second.
    Proves the training mechanism is wired correctly end-to-end; it does
    NOT validate real Wan2.2 output quality - that requires real
    downloaded weights and a real GPU (see `training.hf_download` and
    docs/EXECUTION_PLAN_FIRST_GPU_RUN.md)."""
    return Wan22DiffusersBackend(base_model_id=base_model_id, smoke_test=True, learning_rate=learning_rate, seed=seed)


def build_real_backend(
    *,
    base_model_id: str,
    model_sources: dict[str, Wan22ModelSource],
    device: str = "cuda",
    learning_rate: float = 1e-4,
    batch_encoder: Wan22BatchEncoder | None = None,
) -> Wan22DiffusersBackend:
    """Wires a `Wan22DiffusersBackend` at real Wan2.2 scale, pointed at
    real weight locations - typically the local directory
    `training.hf_download.resolve_local_weights()` returns after a real
    download. `batch_encoder` defaults to a real-shaped
    `RandomLatentBatchEncoder` (real training step, synthetic input)
    until a real `DiffusersBatchEncoder` is built from the same weights'
    VAE/tokenizer/text-encoder and passed in explicitly - see
    docs/EXECUTION_PLAN_FIRST_GPU_RUN.md for that remaining manual step.
    """
    return Wan22DiffusersBackend(
        base_model_id=base_model_id,
        model_sources=model_sources,
        device=device,
        learning_rate=learning_rate,
        batch_encoder=batch_encoder,
    )
