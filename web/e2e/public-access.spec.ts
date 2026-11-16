import { expect, test } from "@playwright/test";

test("dashboard opens publicly without a login gate", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByText("Public read-only dashboard · no account required · uploads and staff administration are disabled.")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Dashboard navigation" })).toBeVisible();
  await expect(page.getByRole("link", { name: /sign up|register|create account|sign in|log in/i })).toHaveCount(0);
});

test("legacy login URL returns visitors to the public dashboard", async ({ page }) => {
  await page.goto("/login");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByText("Public read-only dashboard · no account required · uploads and staff administration are disabled.")).toBeVisible();
});

test("public CSV export works without a session and carries provenance", async ({ request }) => {
  const response = await request.get("/api/export?discipline=batting&limit=30");
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("text/csv");
  expect(await response.text()).toContain("# dataset:");
});

test("public dashboard does not make staff invitation APIs anonymous", async ({ request }) => {
  const response = await request.post("/api/admin/invitations", {
    headers: { origin: "http://127.0.0.1:3000", "content-type": "application/json" },
    data: { email: "visitor@example.org", role: "viewer" },
  });
  expect([401, 403, 503]).toContain(response.status());
});
