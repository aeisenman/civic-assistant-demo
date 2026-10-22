/**
 * The "Apply for a permit" and "Apply for a short-term rental license" quick
 * actions render their inline form, and each form files a real application that
 * comes back with the right tracking prefix.
 *
 * The submit itself is template-only: POST /api/applications in
 * api/app/api/applications.py validates the fields and calls the workflow engine,
 * with no model in the path. The quick action that opens the form does take one
 * chat turn, which is why these carry the suite's long timeouts.
 */

import { expect, test } from "@playwright/test";
import { openChat, waitForApi } from "./helpers";

test.beforeAll(async ({ request }) => {
  await waitForApi(request);
});

test("apply for a permit through the inline form", async ({ page }) => {
  await openChat(page);

  await page.getByTestId("quick-action").filter({ hasText: "Apply for a permit" }).click();

  const form = page.getByTestId("inline-form");
  await expect(form).toBeVisible({ timeout: 85_000 });
  await expect(form).toContainText("Permit");

  // The five fields the API marks required.
  await form.getByTestId("field-applicant_name").fill("Dana Alvarez");
  await form.getByTestId("field-project_address").fill("1234 Cedar St");
  await form.getByTestId("field-permit_type").fill("Building Permit with Plans");
  await form
    .getByTestId("field-project_description")
    .fill("Convert an attached garage into a studio, including electrical.");
  await form.getByTestId("field-valuation_usd").fill("45000");

  await form.getByTestId("form-submit").click();

  const card = page.getByTestId("tracking-card");
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card.getByTestId("tracking-number")).toContainText("PRM-2026-");
});

test("apply for a STRO licence through the inline form", async ({ page }) => {
  await openChat(page);

  await page
    .getByTestId("quick-action")
    .filter({ hasText: "Apply for a short-term rental license" })
    .click();

  const form = page.getByTestId("inline-form");
  await expect(form).toBeVisible({ timeout: 85_000 });
  await expect(form).toHaveAttribute("data-form-type", "stro");

  // A Tier 2 host: home-sharing, so the host lives on site. The validator sends
  // a Tier 2 back as needs_info without that checkbox, which would still mint a
  // tracking number — filling it is what makes this a clean filing.
  await form.getByTestId("field-host_name").fill("Marisol Vega");
  await form.getByTestId("field-contact_email").fill("marisol.vega@example.com");
  await form.getByTestId("field-contact_phone").fill("619-555-0148");
  await form.getByTestId("field-property_address").fill("3182 Bayview Terrace");
  await form.getByTestId("field-unit_type").selectOption("single_family");
  await form.getByTestId("field-tier").selectOption("tier2");
  await form.getByTestId("field-host_resides_onsite").check();
  await form.getByTestId("field-nights_offered_per_year").fill("120");
  await form.getByTestId("field-owner_or_agent").selectOption("owner");
  await form.getByTestId("field-tot_certificate_number").fill("TOT-2026-4417");
  await form.getByTestId("field-rental_unit_btc_number").fill("RUBT-2026-9032");
  await form.getByTestId("field-local_contact_name").fill("Ana Vega");
  await form.getByTestId("field-local_contact_phone").fill("619-555-0199");
  await form.getByTestId("field-attestation_accepted").check();

  await form.getByTestId("form-submit").click();

  const card = page.getByTestId("tracking-card");
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card.getByTestId("tracking-number")).toContainText("STR-2026-");
  // `submitted`, not `routed`: POST /api/applications returns the row as it was
  // written, and the worker does the validating/routing pass a tick later. The
  // card is the one the resident sees at that instant, so that is what is
  // asserted — the department lands on it only for a type the validator has
  // already priced, which is a staff-queue assertion, not a form one.
  await expect(card).toContainText("submitted");
});
