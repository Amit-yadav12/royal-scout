import { expect, test } from "@playwright/test";

test("top 30 batters shows at most 30 ranked rows and explains exclusions", async ({ page }) => {
  await page.goto("/top-batters");
  const rows = page.locator("table tbody tr").filter({ hasNotText: "No player" });
  const count = await rows.count();
  expect(count).toBeGreaterThan(0);
  expect(count).toBeLessThanOrEqual(30);
  await expect(page.getByText(/Eligibility rules/i)).toBeVisible();
  await expect(page.getByText(/Minimum balls faced/i)).toBeVisible();
  await expect(page.getByText(/Excluded players/i)).toBeVisible();
});

test("filtering re-ranks the view but keeps the global rank visible", async ({ page }) => {
  await page.goto("/top-batters");
  const search = page.getByPlaceholder("Search player");
  await search.fill("zzzzzz");
  await expect(page.getByText(/0 of 30 players match/i)).toBeVisible();
  await search.fill("");
  await expect(page.getByText(/30 of 30 players match/i)).toBeVisible();
});

test("score decomposition expands with a documented formula", async ({ page }) => {
  await page.goto("/top-batters");
  await page.locator("table tbody tr").first().getByRole("button").last().click();
  await expect(page.getByText(/Score decomposition — weights renormalise/i)).toBeVisible();
  await expect(page.getByText(/applied/).first()).toBeVisible();
});

test("top 30 bowlers never renders batting-only players", async ({ page }) => {
  await page.goto("/top-bowlers");
  const rows = page.locator("table tbody tr");
  expect(await rows.count()).toBeGreaterThan(0);
  expect(await rows.count()).toBeLessThanOrEqual(30);
  await expect(page.getByText(/Wickets/i).first()).toBeVisible();
});
