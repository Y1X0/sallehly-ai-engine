import { expect, test } from "@playwright/test";

function uniqueEmail(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}@example.com`;
}

async function registerAndLogIn(page: import("@playwright/test").Page, email: string) {
  await page.goto("/login");
  await page.getByText("Need an account? Register").click();
  await page.fill("#email", email);
  await page.fill("#password", "hunter22");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL("/");
}

test("full project lifecycle: create -> plan -> approve storyboard -> approve render -> generate -> assets", async ({
  page,
}) => {
  await registerAndLogIn(page, uniqueEmail("lifecycle"));

  await page.fill("#prompt", "A 12-second warm premium product ad for a minimalist watch");
  await page.fill("#duration", "12");
  await page.selectOption("#aspect-ratio", "16:9");
  await page.getByRole("button", { name: "Create project" }).click();
  await page.waitForURL(/\/projects\/proj_/);

  await page.getByRole("button", { name: "Generate creative plan" }).click();
  await expect(page.getByText("Review the storyboard")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("heading", { name: "Story", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Storyboard", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Approve" }).first().click();
  await expect(page.getByText("Review the render plan")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("heading", { name: "Render plan", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Approve" }).first().click();
  await expect(page.getByRole("button", { name: "Start generation" })).toBeVisible({ timeout: 15_000 });

  await page.getByRole("button", { name: "Start generation" }).click();
  await expect(page.getByText("Generation jobs")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Completed").first()).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Asset library")).toBeVisible({ timeout: 10_000 });
});

test("rejecting the storyboard with feedback regenerates it and stays at the storyboard gate", async ({ page }) => {
  await registerAndLogIn(page, uniqueEmail("reject"));

  await page.fill("#prompt", "A calm minimalist tea ad");
  await page.fill("#duration", "10");
  await page.getByRole("button", { name: "Create project" }).click();
  await page.waitForURL(/\/projects\/proj_/);

  await page.getByRole("button", { name: "Generate creative plan" }).click();
  await expect(page.getByText("Review the storyboard")).toBeVisible({ timeout: 15_000 });

  await page.getByRole("button", { name: "Request changes" }).click();
  await page.fill("textarea", "too static, add more camera movement");
  await page.getByRole("button", { name: "Submit feedback" }).click();

  // Still at the storyboard gate after the regeneration completes.
  await expect(page.getByText("Review the storyboard")).toBeVisible({ timeout: 15_000 });
});

test("project routes require authentication - unauthenticated visitors are redirected to /login", async ({
  page,
}) => {
  await page.goto("/");
  await page.waitForURL("**/login");
  await expect(page.getByRole("heading", { name: "Log in" })).toBeVisible();
});

test("a second account cannot see the first account's projects", async ({ page }) => {
  await registerAndLogIn(page, uniqueEmail("owner"));
  await page.fill("#prompt", "owner-only project");
  await page.fill("#duration", "8");
  await page.getByRole("button", { name: "Create project" }).click();
  await page.waitForURL(/\/projects\/proj_/);

  await page.getByRole("button", { name: "Log out" }).click();
  await page.waitForURL("**/login");
  await registerAndLogIn(page, uniqueEmail("other"));
  await expect(page.getByText("No projects yet - create one to get started.")).toBeVisible();
});
