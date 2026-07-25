import { afterEach, describe, expect, it, vi } from "vitest";
import {
  analyzeCinematicConsistency,
  ApiError,
  approveRepair,
  createProject,
  finalizeProject,
  getCinematicReport,
  getProject,
  getRenderManifest,
  improvePrompt,
  listProjects,
  listRepairs,
  login,
  register,
  rejectRepair,
  repairShot,
  uploadAsset,
} from "./apiClient";

function mockFetchOnce(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => body,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiClient", () => {
  it("register posts to /auth/register with a JSON body and no auth header", async () => {
    const fetchMock = mockFetchOnce(201, { user_id: "u1", email: "a@b.com", workspace_id: "ws_u1", created_at: "now" });

    const user = await register("a@b.com", "hunter22");

    expect(user.user_id).toBe("u1");
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/auth/register");
    expect(options.headers.Authorization).toBeUndefined();
    expect(JSON.parse(options.body)).toEqual({ email: "a@b.com", password: "hunter22" });
  });

  it("login returns the token and user from the response", async () => {
    mockFetchOnce(200, { token: "tok123", user: { user_id: "u1", email: "a@b.com", workspace_id: "ws_u1", created_at: "now" } });

    const result = await login("a@b.com", "hunter22");

    expect(result.token).toBe("tok123");
    expect(result.user.user_id).toBe("u1");
  });

  it("attaches the Authorization header for token-scoped calls", async () => {
    const fetchMock = mockFetchOnce(200, { projects: [] });

    await listProjects("my-token");

    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers.Authorization).toBe("Bearer my-token");
  });

  it("createProject sends the request body and returns the created project", async () => {
    const fetchMock = mockFetchOnce(201, { project_id: "proj_1", status: "created" });

    const project = await createProject("tok", {
      prompt: "a product ad",
      target_duration_sec: 10,
      aspect_ratio: "16:9",
    });

    expect(project.project_id).toBe("proj_1");
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/projects");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body).prompt).toBe("a product ad");
  });

  it("getProject issues a GET request to the right path", async () => {
    const fetchMock = mockFetchOnce(200, { project_id: "proj_1" });

    await getProject("tok", "proj_1");

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/projects/proj_1");
    expect(options.method).toBe("GET");
  });

  it("throws ApiError with the response's status and detail message on failure", async () => {
    mockFetchOnce(409, { detail: "Project proj_1 is completed, expected failed" });

    await expect(getProject("tok", "proj_1")).rejects.toMatchObject({
      status: 409,
      message: "Project proj_1 is completed, expected failed",
    });
  });

  it("throws an ApiError instance specifically, not a generic Error", async () => {
    mockFetchOnce(401, { detail: "Missing or malformed Authorization header" });

    await expect(getProject("bad-token", "proj_1")).rejects.toBeInstanceOf(ApiError);
  });

  it("uploadAsset sends a multipart form without a Content-Type header (browser sets the boundary)", async () => {
    const fetchMock = mockFetchOnce(201, { asset_id: "asset_1", kind: "image" });
    const file = new File(["fake-bytes"], "ref.png", { type: "image/png" });

    const asset = await uploadAsset("tok", file, "proj_1");

    expect(asset.asset_id).toBe("asset_1");
    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers["Content-Type"]).toBeUndefined();
    expect(options.body).toBeInstanceOf(FormData);
  });

  it("finalizeProject posts to /finalize with a null export_spec by default", async () => {
    const fetchMock = mockFetchOnce(200, { project_id: "proj_1", status: "post_processing" });

    const project = await finalizeProject("tok", "proj_1");

    expect(project.status).toBe("post_processing");
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/projects/proj_1/finalize");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ export_spec: null });
  });

  it("finalizeProject forwards a custom export_spec", async () => {
    const fetchMock = mockFetchOnce(200, { project_id: "proj_1", status: "post_processing" });

    await finalizeProject("tok", "proj_1", { format: "mov", quality_preset: "4k" });

    const [, options] = fetchMock.mock.calls[0];
    expect(JSON.parse(options.body)).toEqual({ export_spec: { format: "mov", quality_preset: "4k" } });
  });

  it("getRenderManifest issues a GET request to the right path", async () => {
    const fetchMock = mockFetchOnce(200, { manifest_id: "manifest_1", video: { uri: "file:///x.mp4" } });

    const manifest = await getRenderManifest("tok", "proj_1");

    expect(manifest.manifest_id).toBe("manifest_1");
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/projects/proj_1/render-manifest");
    expect(options.method ?? "GET").toBe("GET");
  });

  it("analyzeCinematicConsistency POSTs to the analyze endpoint and returns the report", async () => {
    const fetchMock = mockFetchOnce(200, { shots_analyzed: 3, scores: { overall: 0.9 } });

    const report = await analyzeCinematicConsistency("tok", "proj_1");

    expect(report.shots_analyzed).toBe(3);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/projects/proj_1/cinematic/analyze");
    expect(options.method).toBe("POST");
  });

  it("getCinematicReport GETs the report endpoint", async () => {
    const fetchMock = mockFetchOnce(200, { shots_analyzed: 3, scores: { overall: 0.9 } });

    await getCinematicReport("tok", "proj_1");

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/projects/proj_1/cinematic/report");
    expect(options.method ?? "GET").toBe("GET");
  });

  it("improvePrompt POSTs to the shot's improve endpoint", async () => {
    const fetchMock = mockFetchOnce(200, { version: 2, positive_prompt: "improved" });

    const improved = await improvePrompt("tok", "proj_1", "shot_1");

    expect(improved.version).toBe(2);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/projects/proj_1/cinematic/prompts/shot_1/improve");
    expect(options.method).toBe("POST");
  });

  it("repairShot POSTs to the shot's repair endpoint", async () => {
    const fetchMock = mockFetchOnce(200, { repair_id: "repair_1", shot_id: "shot_1", review_status: "pending" });

    const action = await repairShot("tok", "proj_1", "shot_1");

    expect(action.repair_id).toBe("repair_1");
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/projects/proj_1/cinematic/repair/shot_1");
    expect(options.method).toBe("POST");
  });

  it("listRepairs GETs the repairs list", async () => {
    const fetchMock = mockFetchOnce(200, { repairs: [{ repair_id: "repair_1" }] });

    const result = await listRepairs("tok", "proj_1");

    expect(result.repairs).toHaveLength(1);
    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain("/projects/proj_1/cinematic/repairs");
  });

  it("approveRepair and rejectRepair POST to their respective endpoints", async () => {
    const approveFetch = mockFetchOnce(200, { repair_id: "repair_1", review_status: "approved" });
    const approved = await approveRepair("tok", "proj_1", "repair_1");
    expect(approved.review_status).toBe("approved");
    const [approveUrl, approveOptions] = approveFetch.mock.calls[0];
    expect(approveUrl).toContain("/projects/proj_1/cinematic/repairs/repair_1/approve");
    expect(approveOptions.method).toBe("POST");

    const rejectFetch = mockFetchOnce(200, { repair_id: "repair_1", review_status: "rejected" });
    const rejected = await rejectRepair("tok", "proj_1", "repair_1");
    expect(rejected.review_status).toBe("rejected");
    const [rejectUrl, rejectOptions] = rejectFetch.mock.calls[0];
    expect(rejectUrl).toContain("/projects/proj_1/cinematic/repairs/repair_1/reject");
    expect(rejectOptions.method).toBe("POST");
  });
});
