/**
 * The staff path: pick an in_review application, read its detail panel, walk it
 * approved -> issued, and prove the certificate the API generated is fetchable.
 * Everything here is behind the staff session, so the spec signs in first.
 */

import { expect, test } from "@playwright/test";
import { API_URL, login, waitForApi } from "./helpers";

test.beforeAll(async ({ request }) => {
  await waitForApi(request);
});

test("advances an in_review application to issued", async ({ page }) => {
  await login(page);
  await page.goto("/staff");
  await expect(page.getByTestId("staff-row").first()).toBeVisible({ timeout: 30_000 });

  const row = page.locator('[data-testid="staff-row"][data-status="in_review"]').first();
  await expect(row).toBeVisible({ timeout: 30_000 });
  const tracking = await row.getAttribute("data-tracking");
  await row.click();

  const panel = page.getByTestId("detail-panel");
  await expect(panel).toBeVisible();
  await expect(panel).toContainText(tracking!);
  await expect(panel.getByRole("heading", { name: "Fields" })).toBeVisible();
  await expect(panel.getByRole("heading", { name: "Timeline" })).toBeVisible();

  const pill = panel.getByTestId("status-pill").first();

  await panel.getByTestId("advance-approved").click();
  await expect(pill).toHaveAttribute("data-status", "approved", { timeout: 30_000 });

  await panel.getByTestId("advance-issued").click();
  await expect(pill).toHaveAttribute("data-status", "issued", { timeout: 30_000 });

  const link = panel.getByTestId("certificate-link");
  await expect(link).toBeVisible({ timeout: 30_000 });
  const href = await link.getAttribute("href");
  expect(href).toContain(API_URL);
  // page.request shares the browser context, so the staff cookie goes with it.
  const pdf = await page.request.get(href!);
  expect(pdf.status()).toBe(200);
});
