/**
 * Captures the eight full-page PNGs in e2e/screenshots/ that the design review
 * looks at. Run with `npm run test:e2e:shots`; the files are git-tracked, so a
 * rerun updates them in place. Depends on a live API — these are real answers.
 */

import path from "node:path";
import { expect, test } from "@playwright/test";
import { ask, login, openChat, settleNav, waitForApi } from "./helpers";

const DIR = path.join(__dirname, "screenshots");
const shot = (name: string) => path.join(DIR, name);

test.beforeAll(async ({ request }) => {
  await waitForApi(request);
});

test("01 + 02 + 03 — chat empty, conversation, inline form", async ({ page }) => {
  await openChat(page);
  await settleNav(page);
  await expect(page.getByTestId("empty-state")).toBeVisible();
  await page.screenshot({ path: shot("01-chat-empty.png"), fullPage: true });

  await ask(page, "When is trash picked up at 4521 Adams Ave?");
  await page.getByTestId("trace-toggle").last().click();
  await expect(page.getByTestId("trace-panel")).toBeVisible();
  await page.waitForTimeout(500);
  await page.screenshot({ path: shot("02-chat-conversation.png"), fullPage: true });

  // A fresh conversation so the form shot is not crowded by the answer above.
  await page.getByTestId("new-conversation").click();
  await page.getByTestId("quick-action").filter({ hasText: "Apply for a permit" }).click();
  const form = page.getByTestId("inline-form");
  await expect(form).toBeVisible({ timeout: 85_000 });
  await form.getByTestId("field-applicant_name").fill("Dana Alvarez");
  await form.getByTestId("field-applicant_email").fill("dana.alvarez@example.com");
  await form.getByTestId("field-project_address").fill("1234 Cedar St");
  await form.getByTestId("field-permit_type").fill("Building Permit with Plans");
  await form
    .getByTestId("field-project_description")
    .fill("Convert an attached garage into a studio, including electrical.");
  await form.getByTestId("field-valuation_usd").fill("45000");
  await page.waitForTimeout(300);
  await page.screenshot({ path: shot("03-chat-form.png"), fullPage: true });
});

test("04 + 05 — staff queue and detail panel", async ({ page }) => {
  await login(page);
  await page.goto("/staff");
  await settleNav(page);
  await expect(page.getByTestId("staff-row").first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: shot("04-staff-queue.png"), fullPage: true });

  // Prefer a row a human still has to act on; fall back to the first row.
  const inReview = page.locator('[data-testid="staff-row"][data-status="in_review"]').first();
  const row = (await inReview.count()) ? inReview : page.getByTestId("staff-row").first();
  await row.click();
  await expect(page.getByTestId("detail-panel")).toBeVisible();
  await page.waitForTimeout(500);
  await page.screenshot({ path: shot("05-staff-detail.png"), fullPage: true });
});

test("06 — traces", async ({ page }) => {
  await login(page);
  await page.goto("/staff/traces");
  await settleNav(page);
  await expect(page.getByTestId("trace-row").first()).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("trace-row").first().click();
  await expect(page.getByTestId("trace-detail")).toBeVisible();
  await page.waitForTimeout(500);
  await page.screenshot({ path: shot("06-traces.png"), fullPage: true });
});

test("08 — the reporting dashboard", async ({ page }) => {
  await login(page);
  await page.goto("/staff/dashboard");
  await settleNav(page);
  await expect(page.getByTestId("kpi-tile").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("card-by-day")).toBeVisible();
  await page.waitForTimeout(500);
  await page.screenshot({ path: shot("08-dashboard.png"), fullPage: true });
});

test.describe("mobile", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("07 — chat at 390px", async ({ page }) => {
    await openChat(page);
    await settleNav(page);
    await ask(page, "How do I report a pothole?");
    await page.waitForTimeout(500);
    await page.screenshot({ path: shot("07-mobile-chat.png"), fullPage: true });
  });
});
