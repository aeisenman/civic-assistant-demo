/**
 * What the UI does when the API is unreachable: /staff shows the error with a
 * Retry instead of "Checking your sign-in…" forever, and the health pill goes
 * red and comes back on its own.
 * Run by `npm run test:e2e`; depends on @playwright/test and the web server
 * only — every API call is aborted at the browser, so nothing reaches FastAPI
 * and no model is ever called.
 *
 * `NEXT_PUBLIC_API_URL` is inlined at build time, so pointing the page at a dead
 * port would mean a second build and a second server. Aborting the requests in
 * the browser produces exactly the same thing the page sees — a fetch that
 * rejects, which lib/api turns into ApiError status 0 — against the server that
 * is already running.
 */

import { expect, test } from "@playwright/test";

import { API_URL } from "./helpers";

/** /health is not under /api, so an `**\/api/**` pattern alone would miss it. */
const DEAD = ["**/api/**", `${API_URL}/health`];

async function killApi(page: import("@playwright/test").Page) {
  for (const pattern of DEAD) await page.route(pattern, (route) => route.abort());
}

async function reviveApi(page: import("@playwright/test").Page) {
  for (const pattern of DEAD) await page.unroute(pattern);
}

test("the staff page shows the error and a Retry when the API is down", async ({ page }) => {
  await killApi(page);
  await page.goto("/staff");

  const gate = page.getByTestId("auth-error");
  await expect(gate).toBeVisible({ timeout: 20_000 });
  // The message names the URL it could not reach, so the reader knows what to fix.
  await expect(gate).toContainText("Cannot reach the API");
  await expect(page.getByTestId("auth-retry")).toBeVisible();
  // The old failure mode: a spinner line that never resolves.
  await expect(page.getByTestId("auth-gate")).toHaveCount(0);

  // With the API back, Retry re-asks: nobody is signed in, so /api/auth/me is a
  // 401 and the page redirects to the sign-in form. No model call either way.
  await reviveApi(page);
  await page.getByTestId("auth-retry").click();
  await expect(page).toHaveURL(/\/login/, { timeout: 20_000 });
});

test("the traces page shows the error and a Retry when the API is down", async ({ page }) => {
  await killApi(page);
  await page.goto("/staff/traces");

  await expect(page.getByTestId("auth-error")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("auth-retry")).toBeVisible();
});

test("the health pill goes unreachable and recovers without a reload", async ({ page }) => {
  await killApi(page);
  await page.goto("/");

  const pill = page.getByTestId("health-pill");
  await expect(pill).toHaveAttribute("data-health", "down", { timeout: 20_000 });
  await expect(pill).toContainText("API unreachable");

  // lib/health re-polls every 30 s and clears the cached rejection, so the pill
  // recovers on its own; before this milestone one failure pinned it red for the
  // life of the tab. The generous timeout is that poll window, not slack.
  await reviveApi(page);
  await expect(pill).toHaveAttribute("data-health", "ok", { timeout: 45_000 });
});
