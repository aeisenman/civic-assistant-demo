/**
 * MarkdownLite rendering, with the API stubbed out: pipe tables become a real
 * <table>, only http(s) links become anchors, and hostile input (probe A18)
 * renders inert.
 * Run by `npm run test:e2e`; depends on @playwright/test and the Next dev server
 * only — no API, no model, no spend, because the reply text is a fixed string.
 */

import { expect, test } from "@playwright/test";

import { API_URL } from "./helpers";

// One reply exercising every branch the red team saw the model produce
// (finding 14) plus the two link schemes that must never become an anchor.
const REPLY = [
  "Here is the comparison you asked for.",
  "",
  "| Permit | Fee | Days |",
  "| --- | --- | --- |",
  "| No-Plan | $411.02 | 10 |",
  "| Simple | $137.00 | 1 |",
  "",
  "Details are on [the DSD page](https://www.sandiego.gov/development-services).",
  "",
  "Do not click [this](javascript:alert(1)) or [that](data:text/html,hi).",
].join("\n");

/**
 * Probe A18: the three sinks a reviewer reaches for. None of them is markdown
 * MarkdownLite implements, so each must survive as the literal text the model
 * wrote — React escapes it, and there is no dangerouslySetInnerHTML anywhere in
 * the tree for it to land in.
 */
const HOSTILE = [
  "<script>window.__pwned = 1;</script>",
  "",
  "![seal](data:text/html;base64,PHNjcmlwdD53aW5kb3cuX19wd25lZD0yPC9zY3JpcHQ+)",
  "",
  "<img src=x onerror=\"window.__pwned = 3\">",
  "",
  "Click [here](javascript:window.__pwned=4) or [here](JaVaScRiPt:alert(1)).",
].join("\n");

function stub(reply: string) {
  return {
    reply,
    citations: [],
    actions: [],
    trace: { intent: "permits", tier: "smart", model: "stub", tool_calls: [], calls: [] },
  };
}

const BODY = stub(REPLY);

test.describe("MarkdownLite", () => {
  test.beforeEach(async ({ page }) => {
    // The streaming route is refused so lib/stream falls back to POST /api/chat,
    // which is the simplest thing to stub with a fixed body. 404 is one of the
    // only two statuses that still trigger that fallback (M18).
    await page.route(`${API_URL}/api/chat/stream`, (route) =>
      route.fulfill({ status: 404, body: "not here" }),
    );
    await page.route(`${API_URL}/api/chat`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(BODY) }),
    );
  });

  test("renders a pipe table, safe links only, and no injected HTML", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("composer-input").fill("compare the permit fees");
    await page.getByTestId("send-button").click();

    const bubble = page.getByTestId("message-assistant").first();
    await expect(bubble).toBeVisible({ timeout: 30_000 });

    // The table is a table, not four lines of pipes.
    const table = bubble.locator("table");
    await expect(table).toHaveCount(1);
    await expect(table.locator("thead th")).toHaveText(["Permit", "Fee", "Days"]);
    await expect(table.locator("tbody tr")).toHaveCount(2);
    await expect(table.locator("tbody tr").first().locator("td").nth(1)).toHaveText("$411.02");
    await expect(bubble).not.toContainText("| --- |");

    // Exactly one anchor: the https one, opened safely.
    const links = bubble.locator("a");
    await expect(links).toHaveCount(1);
    await expect(links).toHaveAttribute("href", "https://www.sandiego.gov/development-services");
    await expect(links).toHaveAttribute("rel", "noopener noreferrer");
    await expect(links).toHaveAttribute("target", "_blank");
    await expect(links).toHaveText("the DSD page");

    // javascript: and data: stay as the literal text the model wrote.
    await expect(bubble).toContainText("[this](javascript:alert(1))");
    await expect(bubble).toContainText("[that](data:text/html,hi)");
  });

  test("hostile input renders inert (probe A18)", async ({ page }) => {
    await page.route(`${API_URL}/api/chat`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(stub(HOSTILE)),
      }),
    );

    await page.goto("/");
    // The same three sinks in the resident's own message, which is rendered by
    // the same component in the user bubble.
    await page.getByTestId("composer-input").fill(HOSTILE);
    await page.getByTestId("send-button").click();

    const bubble = page.getByTestId("message-assistant").first();
    await expect(bubble).toBeVisible({ timeout: 30_000 });
    const user = page.getByTestId("message-user").first();

    for (const where of [bubble, user]) {
      // No element was created from any of it: the markup is text.
      await expect(where.locator("script")).toHaveCount(0);
      await expect(where.locator("img")).toHaveCount(0);
      await expect(where.locator("a")).toHaveCount(0);
      // ...and the text is exactly what was written.
      await expect(where).toContainText("<script>window.__pwned = 1;</script>");
      await expect(where).toContainText("![seal](data:text/html;base64,");
      await expect(where).toContainText('<img src=x onerror="window.__pwned = 3">');
      await expect(where).toContainText("[here](javascript:window.__pwned=4)");
      await expect(where).toContainText("[here](JaVaScRiPt:alert(1))");
    }

    // The clinching check: nothing executed.
    expect(await page.evaluate(() => (window as unknown as Record<string, unknown>).__pwned)).toBe(
      undefined,
    );
  });
});
