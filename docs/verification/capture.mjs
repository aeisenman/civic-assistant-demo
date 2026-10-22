/**
 * Standalone Playwright capture for the 2026-09-07 verification pass: photographs
 * the CONTAINER build on http://localhost:3001 (not the e2e dev server on :3002).
 * Run from web/ with `node ../docs/verification/capture.mjs`; depends on the
 * `playwright` package already installed in web/node_modules and a live API on :8080.
 */

import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

// Resolve `playwright` out of web/node_modules: this script deliberately lives in
// docs/verification/, which has no package.json of its own. Run it from web/.
const { chromium } = createRequire(path.join(process.cwd(), "package.json"))("playwright");

const OUT = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.WEB_URL || "http://localhost:3001";
const USER = process.env.STAFF_USERNAME || "staff";
const PASS = process.env.STAFF_PASSWORD || "staff";

const shot = (page, name, fullPage = true) =>
  page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage });

const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

async function settleNav(page) {
  await page.getByTestId("health-pill").waitFor({ state: "visible", timeout: 30_000 });
  await page
    .waitForFunction(
      () => document.querySelector('[data-testid="health-pill"]')?.dataset.health === "ok",
      { timeout: 30_000 },
    )
    .catch(() => log("WARN: health pill never reported ok"));
}

/** Send a message and wait for the assistant bubble count to grow. */
async function ask(page, text, { midShot } = {}) {
  const before = await page.getByTestId("message-assistant").count();
  await page.getByTestId("composer-input").fill(text);
  await page.getByTestId("send-button").click();
  if (midShot) {
    await page.waitForTimeout(1500);
    await shot(page, midShot);
    log(`mid-stream shot ${midShot}`);
  }
  await page
    .locator('[data-testid="message-assistant"]')
    .nth(before)
    .waitFor({ state: "visible", timeout: 120_000 });
  // The bubble appears as soon as the first token lands; wait for the trace
  // toggle, which the UI only renders once the turn is done.
  await page.getByTestId("trace-toggle").last().waitFor({ state: "visible", timeout: 120_000 });
  await page.waitForTimeout(600);
}

const browser = await chromium.launch();

// ---------- desktop ----------
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();

await page.goto(BASE);
await page.getByTestId("composer-input").waitFor({ state: "visible", timeout: 30_000 });
await settleNav(page);
await page.waitForTimeout(400);
await shot(page, "01-chat-empty");
log("01 empty");

await ask(page, "Where do I go to dispute a parking ticket?", { midShot: "02-chat-streaming" });
await shot(page, "03-chat-answer-with-citations");
log("03 answer");

await page.getByTestId("new-conversation").click();
await page.waitForTimeout(400);
await ask(page, "Who is my council member if I live at 202 C St?");
await shot(page, "04-chat-live-council");
log("04 council");

await page.getByTestId("trace-toggle").last().click();
await page.getByTestId("trace-panel").waitFor({ state: "visible", timeout: 15_000 });
await page.waitForTimeout(500);
await shot(page, "05-chat-trace-panel");
log("05 trace panel");

await page.getByTestId("new-conversation").click();
await page.waitForTimeout(400);
await page.getByTestId("composer-input").fill("I want to apply for a business tax certificate");
await page.getByTestId("send-button").click();
await page.getByTestId("inline-form").waitFor({ state: "visible", timeout: 120_000 });
await page.waitForTimeout(800);
await shot(page, "06-chat-inline-form");
log("06 inline form");

await page.goto(`${BASE}/login`);
await page.getByTestId("login-username").waitFor({ state: "visible", timeout: 30_000 });
await page.waitForTimeout(400);
await shot(page, "07-login");
log("07 login");

await page.getByTestId("login-username").fill(USER);
await page.getByTestId("login-password").fill(PASS);
await page.getByTestId("login-submit").click();
await page.getByTestId("nav-staff-identity").waitFor({ state: "visible", timeout: 30_000 });

await page.goto(`${BASE}/staff`);
await page.getByTestId("staff-row").first().waitFor({ state: "visible", timeout: 30_000 });
await settleNav(page);
await page.waitForTimeout(600);
await shot(page, "08-staff-queue");
log("08 staff queue");

const inReview = page.locator('[data-testid="staff-row"][data-status="in_review"]').first();
const row = (await inReview.count()) ? inReview : page.getByTestId("staff-row").first();
await row.click();
await page.getByTestId("detail-panel").waitFor({ state: "visible", timeout: 15_000 });
await page.waitForTimeout(600);
await shot(page, "09-staff-detail");
log("09 staff detail");

await page.goto(`${BASE}/traces`);
await page.getByTestId("trace-row").first().waitFor({ state: "visible", timeout: 30_000 });
await page.getByTestId("trace-row").first().click();
await page.getByTestId("trace-detail").waitFor({ state: "visible", timeout: 15_000 });
await page.waitForTimeout(600);
await shot(page, "10-traces");
log("10 traces");

// ---------- mobile ----------
const mctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
const mpage = await mctx.newPage();
await mpage.goto(BASE);
await mpage.getByTestId("composer-input").waitFor({ state: "visible", timeout: 30_000 });
await settleNav(mpage);
await ask(mpage, "Where do I go to dispute a parking ticket?");
await shot(mpage, "11-mobile-chat");
log("11 mobile chat");

await browser.close();
log("done");
