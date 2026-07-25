from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HairProfile:
    color: str | None = None
    style: str | None = None
    length: str | None = None


@dataclass(frozen=True)
class CharacterAttributes:
    """Mirrors CharacterIdentityProfile.identity in
    character_identity_profile.schema.json - the attributes that must
    never drift between shots."""

    face_description: str
    age_range: str
    skin_tone: str
    hair: HairProfile = field(default_factory=HairProfile)
    clothing_default: str | None = None
    accessories: tuple[str, ...] = ()
    proportions: str | None = None


@dataclass(frozen=True)
class ExpressionEntry:
    expression: str
    reference_asset_id: str | None = None


@dataclass(frozen=True)
class LoraBinding:
    """Prepared, not implemented - see IReferenceConditioningAdapter and
    docs/adr/0013-cinematic-intelligence-layer.md. Recording a binding
    here does not cause any engine adapter to load LoRA weights today."""

    lora_id: str
    weight: float = 1.0


@dataclass(frozen=True)
class CharacterIdentityProfile:
    """Mirrors packages/schemas/json/character_identity_profile.schema.json.
    Immutable once created (locked=True) - a correction produces a new
    RepairAction against the shots that used it, never an in-place edit
    of this profile."""

    schema_version: str
    character_id: str
    project_id: str
    display_name: str
    identity: CharacterAttributes
    expression_bank: tuple[ExpressionEntry, ...] = ()
    reference_image_ids: tuple[str, ...] = ()
    consistency_seed: int | None = None
    lora_binding: LoraBinding | None = None
    locked: bool = True
    created_at: str | None = None


@dataclass(frozen=True)
class ObjectAttributes:
    materials: tuple[str, ...] = ()
    colors: tuple[str, ...] = ()
    damage_state: str = "pristine"
    size_notes: str | None = None


@dataclass(frozen=True)
class ObjectLocationEntry:
    scene_id: str
    shot_id: str
    location: str


@dataclass(frozen=True)
class ObjectProfile:
    """Mirrors packages/schemas/json/object_profile.schema.json."""

    schema_version: str
    object_id: str
    project_id: str
    name: str
    attributes: ObjectAttributes = field(default_factory=ObjectAttributes)
    location_history: tuple[ObjectLocationEntry, ...] = ()
    reference_image_ids: tuple[str, ...] = ()
    created_at: str | None = None


@dataclass(frozen=True)
class EnvironmentProfile:
    """Mirrors packages/schemas/json/environment_profile.schema.json."""

    schema_version: str
    environment_id: str
    project_id: str
    name: str
    weather: str | None = None
    time_of_day: str | None = None
    season: str | None = None
    architecture: str | None = None
    layout: str | None = None
    sky: str | None = None
    fog: bool = False
    camera_geography_notes: str | None = None
    reference_image_ids: tuple[str, ...] = ()
    first_established_scene_id: str | None = None
    created_at: str | None = None


@dataclass(frozen=True)
class ContinuityViolation:
    violation_type: str
    severity: str
    description: str
    shot_id: str | None = None
    related_shot_id: str | None = None


@dataclass(frozen=True)
class ContinuityReport:
    """Mirrors packages/schemas/json/continuity_report.schema.json. Shared
    output shape for both the Scene Continuity Engine and the Camera
    Continuity Engine (`scope` discriminates)."""

    schema_version: str
    report_id: str
    project_id: str
    scope: str  # "scene" | "camera" | "shot_transition"
    subject_id: str
    passed: bool
    violations: tuple[ContinuityViolation, ...] = ()
    generated_at: str | None = None


@dataclass(frozen=True)
class GrainSetting:
    enabled: bool = False
    intensity: str = "subtle"


@dataclass(frozen=True)
class BloomSetting:
    enabled: bool = False
    intensity: str = "subtle"


@dataclass(frozen=True)
class StyleLock:
    """Mirrors packages/schemas/json/style_lock.schema.json. `base_style`
    is a dict (StyleSetup, style.schema.json) rather than an imported
    dataclass - this package has zero cross-package dependencies, same
    rule video-composition-sdk follows, so embedded foreign schemas stay
    as dicts at this boundary (see ADR 0009's dict-first-at-boundary
    precedent)."""

    schema_version: str
    style_lock_id: str
    project_id: str
    base_style: dict[str, Any]
    film_stock: str | None = None
    grain: GrainSetting = field(default_factory=GrainSetting)
    depth_of_field_target: str = "medium"
    bloom: BloomSetting = field(default_factory=BloomSetting)
    lens_effects: tuple[str, ...] = ()
    lighting_language: str | None = None
    locked: bool = True
    created_at: str | None = None


@dataclass(frozen=True)
class ReferenceImageEntry:
    asset_id: str
    role: str  # "primary" | "angle" | "detail" | "pose" | "mood"
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConditioningReadiness:
    controlnet: bool = False
    ip_adapter: bool = False


@dataclass(frozen=True)
class ReferencePackage:
    """Mirrors packages/schemas/json/reference_package.schema.json."""

    schema_version: str
    package_id: str
    project_id: str
    kind: str  # "character" | "object" | "environment" | "style" | "pose"
    images: tuple[ReferenceImageEntry, ...]
    subject_id: str | None = None
    prepared_for: ConditioningReadiness = field(default_factory=ConditioningReadiness)
    created_at: str | None = None


@dataclass(frozen=True)
class PromptSourceContext:
    character_ids: tuple[str, ...] = ()
    object_ids: tuple[str, ...] = ()
    environment_id: str | None = None
    style_lock_id: str | None = None
    camera_notes: str | None = None
    continuity_notes: str | None = None


@dataclass(frozen=True)
class PromptScore:
    adherence_estimate: float
    length_score: float
    redundancy_score: float
    overall: float


@dataclass(frozen=True)
class PromptPackage:
    """Mirrors packages/schemas/json/prompt_package.schema.json - the
    Prompt Intelligence Engine's output, consumed by the Render
    Configuration Compiler to fill RenderSpec.positive_prompt/
    negative_prompt (render_configuration.schema.json is unchanged)."""

    schema_version: str
    prompt_id: str
    project_id: str
    shot_id: str
    version: int
    positive_prompt: str
    negative_prompt: str
    source_context: PromptSourceContext
    engine_id: str | None = None
    translated_prompt: str | None = None
    compressed: bool = False
    score: PromptScore | None = None
    created_at: str | None = None


@dataclass(frozen=True)
class MemoryEvent:
    event_id: str
    shot_id: str
    scene_id: str
    summary: str
    character_ids: tuple[str, ...] = ()
    object_ids: tuple[str, ...] = ()
    environment_id: str | None = None
    order: int | None = None


@dataclass(frozen=True)
class CameraMemoryState:
    shot_id: str
    camera: dict[str, Any]


@dataclass(frozen=True)
class TimelineEntry:
    shot_id: str
    scene_id: str
    order: int
    summary: str | None = None


@dataclass(frozen=True)
class ProjectMemory:
    """Mirrors packages/schemas/json/project_memory.schema.json - the
    Temporal Memory Engine's per-project state, updated after every
    generated shot. A summary/index of ids, not the full profiles
    themselves (those remain the source of truth in their own stores)."""

    schema_version: str
    project_id: str
    character_ids: tuple[str, ...] = ()
    object_ids: tuple[str, ...] = ()
    environment_ids: tuple[str, ...] = ()
    style_lock_id: str | None = None
    events: tuple[MemoryEvent, ...] = ()
    last_camera_state: CameraMemoryState | None = None
    timeline: tuple[TimelineEntry, ...] = ()
    updated_at: str | None = None


@dataclass(frozen=True)
class QualityScores:
    identity_consistency: float
    camera_consistency: float
    lighting_consistency: float
    style_consistency: float
    composition_quality: float
    prompt_adherence: float
    motion_quality: float
    overall: float


@dataclass(frozen=True)
class QualityIssue:
    category: str
    severity: str
    description: str


@dataclass(frozen=True)
class QualityReport:
    """Mirrors packages/schemas/json/quality_report.schema.json.
    `embeddings_used` is always False in Phase 7 - see
    IEmbeddingProvider."""

    schema_version: str
    report_id: str
    project_id: str
    shot_id: str
    scores: QualityScores
    issues: tuple[QualityIssue, ...] = ()
    repair_recommended: bool = False
    embeddings_used: bool = False
    generated_at: str | None = None


@dataclass(frozen=True)
class RepairAction:
    """Mirrors packages/schemas/json/repair_action.schema.json. Always
    scoped to exactly one shot_id - the Automatic Repair Engine never
    regenerates a whole project."""

    schema_version: str
    repair_id: str
    project_id: str
    shot_id: str
    quality_report_id: str
    repair_type: str
    strategy_id: str
    status: str = "proposed"
    description: str | None = None
    before_summary: str | None = None
    after_summary: str | None = None
    applied_at: str | None = None


@dataclass(frozen=True)
class GraphNode:
    """Mirrors packages/schemas/json/graph_node.schema.json."""

    node_id: str
    project_id: str
    type: str  # "character" | "object" | "location" | "event" | "style"
    label: str
    ref_id: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    """Mirrors packages/schemas/json/graph_edge.schema.json."""

    edge_id: str
    project_id: str
    type: str  # "appears_in" | "uses" | "wears" | "located_at" | "moves_to" | "speaks_to"
    from_node_id: str
    to_node_id: str
    properties: dict[str, Any] = field(default_factory=dict)
