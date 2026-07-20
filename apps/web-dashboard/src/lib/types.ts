/**
 * TypeScript mirrors of packages/schemas/json/*.schema.json and
 * apps/api's request/response shapes. Kept in lockstep with the JSON
 * Schemas by hand (see docs/api/openapi.yaml) - this is the frontend's
 * one place to update when a backend contract changes.
 */

// ---- packages/schemas/json/user.schema.json ----

export interface User {
  user_id: string;
  email: string;
  workspace_id: string;
  created_at: string;
}

export interface AuthResponse {
  token: string;
  user: User;
}

// ---- packages/schemas/json/project.schema.json ----

export type ProjectStatus =
  | "created"
  | "planning"
  | "waiting_storyboard_approval"
  | "waiting_render_approval"
  | "approved"
  | "rejected"
  | "generating"
  | "completed"
  | "failed";

export type RejectedStage = "storyboard" | "render_plan" | null;

export interface ProjectBrief {
  prompt: string;
  target_duration_sec: number;
  aspect_ratio: string;
  reference_asset_ids?: string[];
  style_preset_id?: string | null;
}

export interface Project {
  project_id: string;
  workspace_id: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  status: ProjectStatus;
  rejected_stage: RejectedStage;
  brief: ProjectBrief;
  generation_job_ids: string[];
  asset_ids: string[];
  error_message: string | null;
}

// ---- packages/schemas/json/{camera,motion,lighting,style}.schema.json ----

export interface CameraSetup {
  shot_type:
    | "extreme_wide"
    | "wide"
    | "medium"
    | "medium_close_up"
    | "close_up"
    | "extreme_close_up"
    | "insert"
    | "pov";
  focal_length_mm_equiv?: number;
  angle?: string;
  movement: {
    type: string;
    speed?: "slow" | "medium" | "fast";
    easing?: "linear" | "ease_in" | "ease_out" | "ease_in_out";
  };
  depth_of_field?: "shallow" | "medium" | "deep";
  notes?: string;
}

export interface MotionSetup {
  subject_motion?: string;
  motion_strength: number;
  easing_curve?: string;
  loopable?: boolean;
}

export interface LightingSetup {
  time_of_day: string;
  mood: string;
  key_light?: { direction?: string; hardness?: "soft" | "hard"; color_temp_kelvin?: number };
  fill_light_ratio?: number;
  rim_light?: boolean;
  volumetric_effects?: { enabled?: boolean; intensity?: "subtle" | "medium" | "strong" };
  grading_direction?: string;
  notes?: string;
}

export interface StyleSetup {
  visual_style: string;
  color_grade?: {
    lut_reference?: string;
    palette?: string[];
    contrast?: "low" | "medium" | "high";
    saturation?: "muted" | "natural" | "vivid";
  };
  consistency_seed?: number;
  reference_image_ids?: string[];
}

// ---- packages/schemas/json/{shot,scene,director_plan}.schema.json ----

export interface Shot {
  shot_id: string;
  order: number;
  duration_sec: number;
  description: string;
  transition_in?: string;
  transition_out?: string;
  camera?: CameraSetup;
  motion?: MotionSetup;
  lighting?: LightingSetup;
  style_override?: StyleSetup;
  storyboard_frame_id?: string;
  asset_references?: string[];
}

export interface Scene {
  scene_id: string;
  order: number;
  summary: string;
  location?: string;
  characters?: string[];
  continuity_notes?: string;
  shots: Shot[];
}

export interface DirectorPlan {
  schema_version: string;
  project_id: string;
  logline: string;
  target_duration_sec: number;
  aspect_ratio: string;
  global_style: StyleSetup;
  negative_prompt_global?: string;
  continuity_notes?: string;
  scenes: Scene[];
}

// ---- packages/schemas/json/storyboard.schema.json ----

export type StoryboardStatus = "draft" | "pending_review" | "approved" | "changes_requested";

export interface StoryboardFrame {
  frame_id: string;
  shot_id: string;
  visual_description: string;
  camera_framing: string;
  lens_choice: string;
  camera_movement: string;
  lighting: string;
  environment: string;
  mood: string;
  transition: string;
  preview_image_asset_id?: string;
}

export interface Storyboard {
  project_id: string;
  director_plan_version: string;
  status: StoryboardStatus;
  frames: StoryboardFrame[];
  reviewer_feedback?: { frame_id?: string; comment?: string }[];
}

// ---- packages/schemas/json/render_configuration.schema.json + render_plan.schema.json ----

export interface RenderSpec {
  schema_version: string;
  shot_id: string;
  duration_sec: number;
  fps: number;
  resolution: string;
  aspect_ratio?: string;
  mode?: "text_to_video" | "image_to_video" | "video_edit";
  positive_prompt: string;
  negative_prompt?: string;
  seed?: number;
  motion_strength?: number;
  camera?: CameraSetup;
  lighting?: LightingSetup;
  conditioning_images?: string[];
  engine_id?: string;
  quality_tier?: "preview" | "standard" | "final";
}

export interface RenderPlan {
  project_id: string;
  director_plan_version: string;
  engine_id: string;
  status: StoryboardStatus;
  render_specs: RenderSpec[];
  reviewer_feedback?: { shot_id?: string; comment?: string }[];
}

// ---- packages/schemas/json/generation_job.schema.json ----

export type GenerationJobStatus = "queued" | "running" | "completed" | "failed";

export interface GenerationJob {
  schema_version: string;
  job_id: string;
  project_id: string;
  shot_id: string;
  render_spec: RenderSpec;
  engine_id: string;
  compute_provider_id: string;
  status: GenerationJobStatus;
  external_job_id?: string;
  output_asset_id?: string;
  error_message?: string;
  retry_count: number;
  created_at: string;
  updated_at: string;
}

export interface JobStatusSummary {
  job_id: string;
  status: GenerationJobStatus;
  retry_count: number;
  error_message: string | null;
}

// ---- packages/schemas/json/asset_record.schema.json ----

export type AssetKind = "video" | "preview" | "metadata" | "image";

export interface AssetVersion {
  version: number;
  uri: string;
  created_at: string;
  metadata?: Record<string, unknown>;
}

export interface AssetRecord {
  schema_version: string;
  asset_id: string;
  project_id: string;
  shot_id?: string;
  kind: AssetKind;
  versions: AssetVersion[];
}

// ---- apps/api request bodies ----

export interface CreateProjectRequest {
  prompt: string;
  target_duration_sec: number;
  aspect_ratio: string;
  reference_asset_ids?: string[];
  style_preset_id?: string;
}

export interface RejectStoryboardRequest {
  feedback: string[];
}

export interface RejectRenderRequest {
  feedback: string[];
  quality_tier?: string;
}
