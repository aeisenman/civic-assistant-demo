/**
 * The observability page: at least one turn is listed, and opening a row shows
 * the reply and the raw tool-call JSON behind it.
 */

import { expect, test } from "@playwright/test";
import { ask, login, openChat, waitForApi } from "./helpers";

test.beforeAll(async ({ request }) => {
  await waitForApi(request);
});

test("lists traces and expands one", async ({ page }) => {
  // Guarantee there is at least one turn to look at, whatever ran before.
  await openChat(page);
  await ask(page, "What are the trash pickup rules?");

  // The traces page is staff-only since M11, and lives in the console since M21.
  await login(page);
  await page.goto("/staff/traces");
  const rows = page.getByTestId("trace-row");
  await expect(rows.first()).toBeVisible({ timeout: 30_000 });
  expect(await rows.count()).toBeGreaterThan(0);

  await rows.first().click();
  const detail = page.getByTestId("trace-detail");
  await expect(detail).toBeVisible();
  await expect(detail).toContainText("Reply");
  await expect(detail.getByTestId("trace-tool-json")).toBeVisible();
  await expect(detail.getByTestId("trace-tool-json")).toContainText(/\[|\{/);
});
