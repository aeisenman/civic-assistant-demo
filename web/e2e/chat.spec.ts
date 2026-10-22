/**
 * One real conversation end to end: empty state, a question that needs a tool,
 * the answer streaming in, the trace panel, citations, and the reset.
 */

import { expect, test } from "@playwright/test";
import { openChat, waitForApi } from "./helpers";

test.beforeAll(async ({ request }) => {
  await waitForApi(request);
});

test("asks about trash pickup and shows its work", async ({ page }) => {
  await openChat(page);

  // Empty state.
  const empty = page.getByTestId("empty-state");
  await expect(empty).toBeVisible();
  await expect(empty).toContainText("City of San Diego");
  await expect(page.getByTestId("quick-action").first()).toBeVisible();

  // Send by hand rather than through ask(), so the streaming half of the turn
  // can be asserted: M12's promise is that words appear before the turn ends.
  await page.getByTestId("composer-input").fill("When is trash picked up at 4521 Adams Ave?");
  await page.getByTestId("send-button").click();

  // The status line says what is happening while the model is still working.
  await expect(page.getByTestId("stream-status")).toBeVisible({ timeout: 30_000 });
  // A partial reply is on screen...
  await expect(page.getByTestId("stream-text")).toContainText(/\w/, { timeout: 60_000 });
  // ...and the trace, which only lands with the `done` event, is not yet there.
  expect(await page.getByTestId("trace-toggle").count()).toBe(0);

  const reply = page.getByTestId("message-assistant").first();
  await expect(reply).toHaveAttribute("data-streaming", "false", { timeout: 85_000 });
  await expect(empty).toBeHidden();
  await expect(reply).toContainText(/Adams|Wednesday|trash/i);

  // Trace: a quiet toggle that expands a routing panel.
  const toggle = page.getByTestId("trace-toggle").last();
  await expect(toggle).toBeVisible();
  await toggle.click();
  const panel = page.getByTestId("trace-panel");
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("Intent");
  await expect(panel).toContainText("Model");
  // The model name is whatever the provider is configured with; assert it is
  // not the em-dash placeholder rather than pinning a model id.
  const modelCell = panel.locator("dd").nth(3);
  await expect(modelCell).not.toHaveText("—");

  // Provenance: either a numbered citation chip or a tool call must be shown.
  const chips = await page.getByTestId("citation-chip").count();
  const tools = await panel.getByTestId("tool-call").count();
  expect(chips + tools).toBeGreaterThan(0);

  // Reset.
  await page.getByTestId("new-conversation").click();
  await expect(page.getByTestId("message-assistant")).toHaveCount(0);
  await expect(page.getByTestId("message-user")).toHaveCount(0);
  await expect(page.getByTestId("empty-state")).toBeVisible();
});
