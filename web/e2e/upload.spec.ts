/**
 * Attach a filled-out permit PDF and send it with no typing: the API extracts
 * the fields and files the application.
 */

import path from "node:path";
import { expect, test } from "@playwright/test";
import { openChat, waitForApi } from "./helpers";

const PDF = path.join(__dirname, "..", "..", "api", "forms", "sample_permit_application.pdf");

test.beforeAll(async ({ request }) => {
  await waitForApi(request);
});

test("uploads a permit PDF and files it", async ({ page }) => {
  await openChat(page);

  await page.getByTestId("upload-input").setInputFiles(PDF);

  const chip = page.getByTestId("attachment-chip");
  await expect(chip).toBeVisible({ timeout: 30_000 });
  await expect(chip).toContainText("chars");

  // No typing: an attachment is a message on its own.
  await page.getByTestId("send-button").click();

  const card = page.getByTestId("tracking-card");
  await expect(card).toBeVisible({ timeout: 85_000 });
  await expect(card.getByTestId("tracking-number")).toContainText("PRM-2026-");
});
