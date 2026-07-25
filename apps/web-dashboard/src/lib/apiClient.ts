import type {
  AssetRecord,
  AuthResponse,
  CinematicReport,
  CreateProjectRequest,
  DirectorPlan,
  GenerationJob,
  JobStatusSummary,
  Project,
  PromptPackage,
  RejectRenderRequest,
  RejectStoryboardRequest,
  RenderManifest,
  RenderPlan,
  RepairAction,
  Storyboard,
  User,
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: { method?: string; token?: string; json?: unknown; body?: FormData } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`;
  }

  let body: BodyInit | undefined;
  if (options.body) {
    body = options.body;
  } else if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? (body ? "POST" : "GET"),
    headers,
    body,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail ?? detail;
    } catch {
      // response body wasn't JSON - fall back to statusText
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

// ---- auth ----

export function register(email: string, password: string): Promise<User> {
  return request<User>("/auth/register", { json: { email, password } });
}

export function login(email: string, password: string): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/login", { json: { email, password } });
}

export function getMe(token: string): Promise<User> {
  return request<User>("/users/me", { token });
}

// ---- projects ----

export function listProjects(token: string): Promise<{ projects: Project[] }> {
  return request("/projects", { token });
}

export function createProject(token: string, body: CreateProjectRequest): Promise<Project> {
  return request<Project>("/projects", { method: "POST", token, json: body });
}

export function getProject(token: string, projectId: string): Promise<Project> {
  return request<Project>(`/projects/${projectId}`, { token });
}

export function generatePlan(token: string, projectId: string): Promise<Project> {
  return request<Project>(`/projects/${projectId}/generate-plan`, { method: "POST", token });
}

export function getPlan(token: string, projectId: string): Promise<DirectorPlan> {
  return request<DirectorPlan>(`/projects/${projectId}/plan`, { token });
}

export function getStoryboard(token: string, projectId: string): Promise<Storyboard> {
  return request<Storyboard>(`/projects/${projectId}/storyboard`, { token });
}

export function approveStoryboard(token: string, projectId: string): Promise<Project> {
  return request<Project>(`/projects/${projectId}/approve-storyboard`, { method: "POST", token });
}

export function rejectStoryboard(
  token: string,
  projectId: string,
  body: RejectStoryboardRequest,
): Promise<Project> {
  return request<Project>(`/projects/${projectId}/reject-storyboard`, { method: "POST", token, json: body });
}

export function getRenderPlan(token: string, projectId: string): Promise<RenderPlan> {
  return request<RenderPlan>(`/projects/${projectId}/render-plan`, { token });
}

export function approveRender(token: string, projectId: string): Promise<Project> {
  return request<Project>(`/projects/${projectId}/approve-render`, { method: "POST", token });
}

export function rejectRender(token: string, projectId: string, body: RejectRenderRequest): Promise<Project> {
  return request<Project>(`/projects/${projectId}/reject-render`, { method: "POST", token, json: body });
}

export function generateVideo(token: string, projectId: string): Promise<Project> {
  return request<Project>(`/projects/${projectId}/generate-video`, { method: "POST", token });
}

export function retryGeneration(token: string, projectId: string): Promise<Project> {
  return request<Project>(`/projects/${projectId}/retry-generation`, { method: "POST", token });
}

export function listAssets(token: string, projectId: string): Promise<{ project_id: string; assets: AssetRecord[] }> {
  return request(`/projects/${projectId}/assets`, { token });
}

export function uploadAsset(token: string, file: File, projectId?: string): Promise<AssetRecord> {
  const form = new FormData();
  form.append("file", file);
  if (projectId) {
    form.append("project_id", projectId);
  }
  return request<AssetRecord>("/assets/upload", { method: "POST", token, body: form });
}

export function finalizeProject(token: string, projectId: string, exportSpec?: Record<string, unknown>): Promise<Project> {
  return request<Project>(`/projects/${projectId}/finalize`, {
    method: "POST",
    token,
    json: { export_spec: exportSpec ?? null },
  });
}

export function getRenderManifest(token: string, projectId: string): Promise<RenderManifest> {
  return request<RenderManifest>(`/projects/${projectId}/render-manifest`, { token });
}

// ---- cinematic intelligence ----

export function analyzeCinematicConsistency(token: string, projectId: string): Promise<CinematicReport> {
  return request<CinematicReport>(`/projects/${projectId}/cinematic/analyze`, { method: "POST", token });
}

export function getCinematicReport(token: string, projectId: string): Promise<CinematicReport> {
  return request<CinematicReport>(`/projects/${projectId}/cinematic/report`, { token });
}

export function improvePrompt(token: string, projectId: string, shotId: string): Promise<PromptPackage> {
  return request<PromptPackage>(`/projects/${projectId}/cinematic/prompts/${shotId}/improve`, {
    method: "POST",
    token,
  });
}

export function repairShot(token: string, projectId: string, shotId: string): Promise<RepairAction> {
  return request<RepairAction>(`/projects/${projectId}/cinematic/repair/${shotId}`, { method: "POST", token });
}

export function listRepairs(token: string, projectId: string): Promise<{ repairs: RepairAction[] }> {
  return request(`/projects/${projectId}/cinematic/repairs`, { token });
}

export function approveRepair(token: string, projectId: string, repairId: string): Promise<RepairAction> {
  return request<RepairAction>(`/projects/${projectId}/cinematic/repairs/${repairId}/approve`, {
    method: "POST",
    token,
  });
}

export function rejectRepair(token: string, projectId: string, repairId: string): Promise<RepairAction> {
  return request<RepairAction>(`/projects/${projectId}/cinematic/repairs/${repairId}/reject`, {
    method: "POST",
    token,
  });
}

// ---- jobs ----

export function getJob(token: string, jobId: string): Promise<GenerationJob> {
  return request<GenerationJob>(`/jobs/${jobId}`, { token });
}

export function getJobStatus(token: string, jobId: string): Promise<JobStatusSummary> {
  return request<JobStatusSummary>(`/jobs/${jobId}/status`, { token });
}
