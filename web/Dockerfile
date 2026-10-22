# Multi-stage build for the Next.js app. `output: "standalone"` in
# next.config.ts means the runner only needs .next/standalone + static assets,
# so the final image carries no node_modules. Built by docker-compose's `web`
# service; listens on 3000 inside the container (published as 3001).
#
# Base pinned to the exact patch (checked 2026-09-14: 22.23.2 is the newest
# 22.x alpine tag on Docker Hub). `node:22-alpine` moved between builds.
FROM node:22.23.2-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# The e2e tests are a dev tool; the image must not pull a Chromium for them.
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
RUN npm ci

FROM node:22.23.2-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* is inlined at build time, so the browser's API URL is baked in
# here, not at runtime. Compose passes the same value as a build arg.
ARG NEXT_PUBLIC_API_URL=http://localhost:8080
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22.23.2-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# The standalone server serves pre-built files and writes nothing, so it has no
# reason to be root. Own name rather than the image's built-in `node` user so
# the two images in this repo are the same shape.
RUN addgroup -S app && adduser -S -G app -u 10001 app

# The standalone server is started with `node server.js`; npm and its bundled
# copies of tar and brace-expansion (which Trivy flags) are never used at
# runtime, so they leave the image. `apk upgrade` pulls Alpine's fixes (openssl
# on 2026-09-16) that the base tag has not picked up yet.
RUN apk upgrade --no-cache \
    && rm -rf /usr/local/lib/node_modules /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack

COPY --from=builder --chown=app:app /app/.next/standalone ./
COPY --from=builder --chown=app:app /app/.next/static ./.next/static
COPY --from=builder --chown=app:app /app/public ./public

USER app

EXPOSE 3000

# Node 22 has a global fetch, and this image has neither curl nor wget.
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=12 \
  CMD node -e "fetch('http://localhost:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
