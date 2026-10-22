/**
 * 390x844 (an iPhone-sized viewport): the composer is reachable and nothing
 * pushes the page sideways.
 */

import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

test("the chat page fits a 390px viewport", async ({ page }) => {
  await page.goto("/");

  const composer = page.getByTestId("composer-input");
  await expect(composer).toBeVisible();
  const box = await composer.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.y).toBeLessThan(844);
  expect(box!.x).toBeGreaterThanOrEqual(0);

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});

test("the staff table scrolls inside its container, not the page", async ({ page }) => {
  await login(page);
  await page.goto("/staff");
  await page.waitForTimeout(1500);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});
