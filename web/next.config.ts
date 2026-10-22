import type { NextConfig } from "next";

/**
 * Standalone output plus the security headers every response carries.
 * Read by `next build` and `next dev`; the Dockerfile copies .next/standalone.
 * Depends on NEXT_PUBLIC_API_URL, which is a build arg (Next inlines it).
 *
 * `agentRules: false` stops `next dev` writing AGENTS.md/CLAUDE.md into web/ —
 * this repo already has its own conventions file at the root — and
 * `devIndicators: false` keeps the dev badge out of the screenshots.
 */

/**
 * The browser talks to the API directly, on a different origin (a different
 * port counts), so `connect-src 'self'` alone would block every fetch. The
 * origin is derived at build time from the same variable lib/api.ts reads, so
 * the CSP can never drift from the URL the code actually calls.
 */
const API_ORIGIN = (() => {
  const raw = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";
  try {
    return new URL(raw).origin;
  } catch {
    return "http://localhost:8080";
  }
})();

const DEV = process.env.NODE_ENV !== "production";

/**
 * One CSP for both builds, with two documented dev-only relaxations.
 *
 * `script-src 'unsafe-inline'`: Next hydrates through inline
 * `self.__next_f.push(...)` scripts with no nonce (a nonce needs middleware and
 * dynamic rendering, which would cost every page its static prerender), so it is
 * required in production too — verified by loading all four pages with it
 * removed and watching them fail to hydrate.
 * `'unsafe-eval'` and `ws:` are added only under `next dev`: Turbopack's HMR
 * client evaluates modules and opens a websocket back to the dev server. The
 * production image never sends either.
 */
const CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${DEV ? " 'unsafe-eval'" : ""}`,
  // Tailwind v4 injects the utility sheet as a <style> element at runtime in dev
  // and React sets inline styles; neither can carry a hash.
  "style-src 'self' 'unsafe-inline'",
  // data: is for the favicon and any inline SVG data URI; no remote images.
  "img-src 'self' data:",
  `connect-src 'self' ${API_ORIGIN}${DEV ? " ws: wss:" : ""}`,
  "font-src 'self' data:",
  // Nothing here is meant to be embedded, and nothing here embeds anything.
  "frame-ancestors 'none'",
  "frame-src 'none'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: CSP },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  // The older header, for browsers that predate frame-ancestors.
  { key: "X-Frame-Options", value: "DENY" },
];

const nextConfig: NextConfig = {
  output: "standalone",
  agentRules: false,
  devIndicators: false,
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

export default nextConfig;
