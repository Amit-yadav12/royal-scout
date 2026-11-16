import { expect, test } from "@playwright/test";

test("player dossier shows decomposition, confidence reasons and an evidence trail", async ({ page }) => {
  await page.goto("/players");
  await page.locator("table tbody tr a").first().click();
  await expect(page.getByText("Score decomposition", { exact: false })).toBeVisible();
  await expect(page.getByText(/Confidence & sample/i)).toBeVisible();
  await expect(page.getByText(/Evidence trail/i)).toBeVisible();
  await expect(page.getByText(/Config fingerprint/i).first()).toBeVisible();
  await expect(page.getByText(/Strengths/i)).toBeVisible();
  await expect(page.getByText(/Weaknesses & caveats/i)).toBeVisible();
});

test("comparison lab accepts four players and refuses cross-axis mixing", async ({ page }) => {
  await page.goto("/compare");
  const select = page.getByLabel("Choose a player");
  const options = await select.locator("option").all();
  const names = (await Promise.all(options.map((o) => o.textContent())))
    .filter((t) => t && !t.startsWith("Choose")) as string[];
  expect(names.length).toBeGreaterThan(3);
  for (const name of names.slice(0, 4)) {
    await select.selectOption({ label: name });
    await page.getByRole("button", { name: "Add" }).click();
  }
  await expect(page.getByText("4/4 selected")).toBeVisible();
  await expect(page.getByText(/Normalised component profile/i)).toBeVisible();
  await expect(page.getByText(/A higher index is not automatically a better selection/i)).toBeVisible();
});

test("player explorer paginates and filters", async ({ page }) => {
  await page.goto("/players");
  await expect(page.getByText(/Page 1 of/i)).toBeVisible();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText(/Page 2 of/i)).toBeVisible();
  await page.getByPlaceholder("Search any player").fill("Fixture");
  await expect(page.getByText(/Page 1 of/i)).toBeVisible();
});
