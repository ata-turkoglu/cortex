import { expect, test } from "@playwright/test";

test("serves the dashboard and processes routes", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await page.goto("/processes");
  await expect(page.getByText("Canlı iş akışı")).toBeVisible();
});

test("restores persisted background work after navigation", async ({ page }) => {
  await page.route("**/api/v1/workflows", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "workflow-1",
          workspace_id: "workspace-1",
          definition_id: "document-ingestion",
          job_type: "ingestion",
          state: "running",
          recovery_state: null,
          created_at: "2026-08-03T00:00:00Z",
          updated_at: "2026-08-03T00:00:00Z",
          finished_at: null,
          steps: [
            {
              id: "step-1",
              step_name: "normalize",
              state: "running",
              retry_count: 0,
              checkpoint_json: null,
            },
          ],
        },
      ]),
    });
  });
  await page.goto("/processes");
  await expect(page.getByText("ingestion — running")).toBeVisible();
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await page.goto("/processes");
  await expect(page.getByText("ingestion — running")).toBeVisible();
});
