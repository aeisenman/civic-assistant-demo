/**
 * Playwright end-to-end config for the resident chat, the staff queue and the
 * trace table. Run with `npm run test:e2e` against a dev server on :3002 and a
 * live API on :8080 — these tests exercise the real LLM, hence the long timeout.
 * Depends on @playwright/test only.
 */

import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL || "http://localhost:3002";
const PORT = new URL(baseURL).port || "3002";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 1,
  // The LLM answers in tens of seconds on a laptop; a short timeout would only
  // measure the model, not the UI.
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "Desktop Chrome",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
  // Only starts a server if nothing is already listening on the port.
  webServer: {
    command: `PORT=${PORT} npm run dev`,
    url: baseURL,
    reuseExistingServer: true,
    timeout: 120_000,
    env: {
      NODE_ENV: "development",
      NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080",
    },
  },
});
