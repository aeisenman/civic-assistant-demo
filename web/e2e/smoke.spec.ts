/**
 * The resident page and the three console pages load, the console nav moves
 * between them, and the health pill goes green once the API answers. The
 * cheapest possible "is anything on fire".
 */

import { expect, test } from "@playwright/test";
import { login, waitForApi } from "./helpers";

test.beforeAll(async ({ request }) => {
  await waitForApi(request);
});

test("the resident page has no staff links, only the footer sign-in", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Ask the City" })).toBeVisible();
  // M21: the resident nav is the seal, the title, the badge and the pill.
  await expect(page.getByTestId("nav-queue")).toHaveCount(0);
  await expect(page.getByTestId("nav-traces")).toHaveCount(0);

  await page.getByTestId("footer-staff-login").click();
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByTestId("login-form")).toBeVisible();
});

test("the staff console nav moves between queue, dashboard and traces", async ({ page }) => {
  await login(page);
  await expect(page).toHaveURL(/\/staff$/);
  await expect(page.getByRole("heading", { name: "Staff queue" })).toBeVisible();

  await page.getByTestId("nav-dashboard").click();
  await expect(page).toHaveURL(/\/staff\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Reporting" })).toBeVisible();

  await page.getByTestId("nav-traces").click();
  await expect(page).toHaveURL(/\/staff\/traces$/);
  await expect(page.getByRole("heading", { name: "Traces" })).toBeVisible();

  await page.getByTestId("nav-queue").click();
  await expect(page).toHaveURL(/\/staff$/);
  await expect(page.getByRole("heading", { name: "Staff queue" })).toBeVisible();
});

test("the old /traces URL still lands on the console", async ({ page }) => {
  await login(page);
  await page.goto("/traces");
  await expect(page).toHaveURL(/\/staff\/traces$/, { timeout: 20_000 });
  await expect(page.getByRole("heading", { name: "Traces" })).toBeVisible();
});

test("the health pill turns green", async ({ page }) => {
  await page.goto("/");
  const pill = page.getByTestId("health-pill");
  await expect(pill).toHaveAttribute("data-health", "ok", { timeout: 30_000 });
  await expect(pill).toContainText("API healthy");
});
