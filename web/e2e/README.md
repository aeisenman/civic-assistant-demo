# e2e — Playwright tests for the web app

Real browser, real API, real model: nothing here is mocked, so a run takes a few
minutes and the per-test timeout is 90 s.

    npm run test:e2e          # all specs, Desktop Chrome 1440x900
    npm run test:e2e:shots    # just the design-review screenshots

Needs the API on `http://localhost:8080` (`docker compose up -d`) and a web dev
server; the config starts `npm run dev` itself unless one is already listening on
the port. Override either with `E2E_BASE_URL` and `NEXT_PUBLIC_API_URL`.

`screenshots/*.png` are committed on purpose — they are the design review record.
`playwright-report/` and `test-results/` are not.
