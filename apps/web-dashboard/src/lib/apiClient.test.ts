import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, createProject, getProject, listProjects, login, register, uploadAsset } from "./apiClient";

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
});
