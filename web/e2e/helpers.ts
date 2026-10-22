/**
 * Shared helpers for the e2e suite: wait for the API, sign a staff member in,
 * and drive one chat turn. Imported by every spec in e2e/. Depends on
 * @playwright/test only.
 */

import { expect, type Page, type APIRequestContext } from "@playwright/test";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

/** Must match STAFF_USERNAME / STAFF_PASSWORD wherever the API under test runs. */
export const STAFF_USERNAME = process.env.STAFF_USERNAME || "staff";
export const STAFF_PASSWORD = process.env.STAFF_PASSWORD || "staff";

/** Poll GET /health until it reports ok, so a restarting API is not a failure. */
export async function waitForApi(request: APIRequestContext, ms = 60_000) {
  const deadline = Date.now() + ms;
  let last = "never answered";
  while (Date.now() < deadline) {
    try {
      const res = await request.get(`${API_URL}/health`, { timeout: 5_000 });
      const body = await res.json();
      if (body?.status === "ok") return body;
      last = JSON.stringify(body);
    } catch (e) {
      last = String(e);
    }
    await new Promise((r) => setTimeout(r, 2_000));
  }
  throw new Error(`API at ${API_URL} never became healthy: ${last}`);
}

/**
 * Sign in through the real form (M11). The HttpOnly cookie the API sets then
 * rides on this browser context, so /staff and /traces answer instead of
 * bouncing to /login. Call it before visiting either page.
 */
export async function login(page: Page) {
  await page.goto("/login");
  await page.getByTestId("login-username").fill(STAFF_USERNAME);
  await page.getByTestId("login-password").fill(STAFF_PASSWORD);
  await page.getByTestId("login-submit").click();
  await expect(page.getByTestId("nav-staff-identity")).toBeVisible({ timeout: 30_000 });
}

/** Type a message, send it, and wait for the assistant bubble that follows. */
export async function ask(page: Page, text: string) {
  const before = await page.getByTestId("message-assistant").count();
  await page.getByTestId("composer-input").fill(text);
  await page.getByTestId("send-button").click();
  await expect(page.getByTestId("message-assistant")).toHaveCount(before + 1, {
    timeout: 85_000,
  });
  return page.getByTestId("message-assistant").nth(before);
}

/** The chat page, ready to type into. */
export async function openChat(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId("composer-input")).toBeVisible();
}

/** Screenshots should not show the health pill mid-check. */
export async function settleNav(page: Page) {
  await expect(page.getByTestId("health-pill")).toHaveAttribute("data-health", "ok", {
    timeout: 30_000,
  });
}
