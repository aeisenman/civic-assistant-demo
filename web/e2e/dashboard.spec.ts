/**
 * The reporting dashboard: it renders real numbers, and the window selector
 * actually re-asks the API for a different window.
 * Run by `npm run test:e2e`; depends on @playwright/test and on an API that
 * serves GET /api/reports/summary. No model is called — signing in and reading
 * a report are both pure SQL.
 */

import { expect, test } from "@playwright/test";
import { login, waitForApi } from "./helpers";

test.beforeAll(async ({ request }) => {
  await waitForApi(request);
});

test("the dashboard renders KPI tiles with numbers in them", async ({ page }) => {
  await login(page);
  await page.goto("/staff/dashboard");

  await expect(page.getByRole("heading", { name: "Reporting" })).toBeVisible();
  const tiles = page.getByTestId("kpi-tile");
  await expect(tiles.first()).toBeVisible({ timeout: 30_000 });
  // Eight: turns, conversations, cost, citation rate, p50, p95, errors, fallbacks.
  await expect(tiles).toHaveCount(8);

  // Every tile shows a figure. An empty window is all zeros, which still counts:
  // what must never happen is a tile rendering "—" or nothing at all.
  for (const text of await tiles.allInnerTexts()) {
    expect(text).toMatch(/\d/);
  }

  // No error banner: the endpoint answered.
  await expect(page.getByTestId("dashboard-error")).toHaveCount(0);
  await expect(page.getByTestId("card-by-day")).toBeVisible();
  await expect(page.getByTestId("card-unanswered")).toBeVisible();
});

test("the window selector re-asks the API for 30 days", async ({ page }) => {
  const asked: string[] = [];
  // Observe, do not stub: the point is that the real request carries days=30.
  await page.route("**/api/reports/summary*", (route) => {
    asked.push(route.request().url());
    return route.continue();
  });

  await login(page);
  await page.goto("/staff/dashboard");
  await expect(page.getByTestId("kpi-tile").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("dashboard-window")).toContainText("Last 7 days");
  expect(asked.at(-1)).toContain("days=7");

  await page.getByTestId("window-30").click();

  // The label and the container attribute both come from the new response, so
  // waiting for them proves the page re-rendered rather than just re-fetched.
  await expect(page.getByTestId("dashboard-window")).toContainText("Last 30 days");
  await expect(page.getByTestId("dashboard")).toHaveAttribute("data-days", "30", {
    timeout: 20_000,
  });
  expect(asked.at(-1)).toContain("days=30");
  await expect(page.getByTestId("window-30")).toHaveAttribute("aria-pressed", "true");

  await page.getByTestId("window-1").click();
  await expect(page.getByTestId("dashboard-window")).toContainText("Last 24 hours");
  expect(asked.at(-1)).toContain("days=1");
});
