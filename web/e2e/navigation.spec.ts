import { expect, test } from "@playwright/test";

const ROUTES: { path: string; heading: string; nav: string }[] = [
  { path: "/", heading: "Overview", nav: "Overview" },
  { path: "/data-center", heading: "Data Center", nav: "Data Center" },
  { path: "/ingestion", heading: "Data Ingestion", nav: "Data Ingestion" },
  { path: "/data-audit", heading: "Data Audit", nav: "Data Audit" },
  { path: "/batting", heading: "Batting Analytics", nav: "Batting Analytics" },
  { path: "/bowling", heading: "Bowling Analytics", nav: "Bowling Analytics" },
  { path: "/top-batters", heading: "Top 30 Batters", nav: "Top 30 Batters" },
  { path: "/top-bowlers", heading: "Top 30 Bowlers", nav: "Top 30 Bowlers" },
  { path: "/pressure", heading: "Pressure Analytics", nav: "Pressure Analytics" },
  { path: "/players", heading: "Player Explorer", nav: "Player Explorer" },
  { path: "/compare", heading: "Player Comparison Lab", nav: "Player Comparison" },
  { path: "/statistical", heading: "Statistical Intelligence", nav: "Statistical Intelligence" },
  { path: "/stability", heading: "Ranking Stability", nav: "Ranking Stability" },
  { path: "/exports", heading: "Export Center", nav: "Export Center" },
  { path: "/methodology", heading: "Methodology & Settings", nav: "Methodology & Settings" },
];

test.describe("every dashboard section renders without console errors", () => {
  for (const route of ROUTES) {
    test(`${route.path} renders "${route.heading}"`, async ({ page }) => {
      const errors: string[] = [];
      page.on("pageerror", (e) => errors.push(String(e)));
      page.on("console", (m) => {
        if (m.type() === "error") errors.push(m.text());
      });
      const response = await page.goto(route.path);
      expect(response?.status()).toBe(200);
      await expect(page.getByRole("heading", { name: route.heading, exact: true })).toBeVisible();
      expect(errors).toEqual([]);
    });
  }
});

test("the sidebar exposes all fifteen sections and navigates", async ({ page }) => {
  await page.goto("/");
  const nav = page.locator("nav");
  for (const route of ROUTES) {
    await expect(nav.getByRole("link", { name: route.nav, exact: true })).toBeVisible();
  }
  await nav.getByRole("link", { name: /Ranking Stability/ }).click();
  await expect(page).toHaveURL(/\/stability$/);
});

test("the ingested dataset is labelled and the audited pressure ranking is reachable", async ({ page }) => {
  await page.goto("/top-batters");
  // the bundle now carries the real SupeRR pack, so no fixture banner is allowed
  await expect(page.getByText("SYNTHETIC TEST DATA")).toHaveCount(0);
  await page.goto("/pressure-audit");
  await expect(page.getByRole("heading", { name: /audited final twenty/i })).toBeVisible();
  await expect(page.getByText("Shashank Singh")).toBeVisible();
  await expect(page.getByText("Mohammad Nawaz")).toBeVisible();
});
