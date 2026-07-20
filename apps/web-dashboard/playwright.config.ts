import { defineConfig, devices } from "@playwright/test";

const API_PORT = 8000;
const WEB_PORT = 3000;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], launchOptions: { executablePath: "/opt/pw-browsers/chromium" } },
    },
  ],
  webServer: [
    {
      // apps/api - the fully offline default stack (LocalHeuristicLLMProvider +
      // Wan21Adapter + LocalProvider), same as tests/test_api.py.
      command: `uv run uvicorn api.main:app --app-dir src --port ${API_PORT}`,
      port: API_PORT,
      cwd: "../api",
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: "npm run dev",
      port: WEB_PORT,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
});
