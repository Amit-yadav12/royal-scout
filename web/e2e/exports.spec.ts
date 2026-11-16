import { expect, test } from "@playwright/test";

test("live CSV export carries a provenance header and 30 or fewer rows", async ({ request }) => {
  const response = await request.get("/api/export?discipline=batting&limit=30");
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("text/csv");
  const body = await response.text();
  const lines = body.split("\n");
  expect(lines[0].startsWith("#")).toBe(true);
  expect(body).toContain("# model_version:");
  expect(body).toContain("# config_fingerprint:");
  expect(body).toContain("# limitations:");
  const dataRows = lines.filter((l) => !l.startsWith("#") && l.trim().length > 0);
  expect(dataRows.length).toBeGreaterThan(1);
  expect(dataRows.length - 1).toBeLessThanOrEqual(30);
});

test("a filtered scope narrows the export and states the scope", async ({ request }) => {
  const global = await (await request.get("/api/export?discipline=bowling&limit=30")).text();
  const scopeLine = global.split("\n").find((l) => l.startsWith("# scope:"));
  expect(scopeLine).toContain("All data");
  // a scope that exists in the ingested SupeRR pack (IPL seasons are always present)
  const label = "IPL 2025";
  const scoped = await request.get("/api/export?discipline=bowling&limit=30&scope=" + encodeURIComponent(label));
  expect(scoped.status()).toBe(200);
  const scopedText = await scoped.text();
  expect(scopedText.split("\n").find((l) => l.startsWith("# scope:"))).toContain(label);
  // a filtered scope must never return more rows than the global leaderboard
  const scopedRows = scopedText.split("\n").filter((l) => !l.startsWith("#") && l.trim()).length - 1;
  const globalRows = global.split("\n").filter((l) => !l.startsWith("#") && l.trim()).length - 1;
  expect(scopedRows).toBeLessThanOrEqual(globalRows);
});

test("health endpoint reports worker configuration honestly", async ({ request }) => {
  const response = await request.get("/api/health");
  expect(response.status()).toBe(200);
  const json = await response.json();
  expect(json.web).toBe("ok");
  expect(["ok", "unavailable", "not_configured"]).toContain(json.worker);
});

test("ingestion endpoint refuses to pretend when the worker is absent", async ({ request }) => {
  const response = await request.post("/api/ingest");
  if (response.status() === 503) {
    const json = await response.json();
    expect(json.error).toMatch(/WORKER_API_URL|not configured/i);
  } else {
    expect([202, 400]).toContain(response.status());
  }
});

test("export centre lists real artefacts with real sizes", async ({ page }) => {
  await page.goto("/exports");
  await expect(page.getByText("Artefacts generated at analysis time")).toBeVisible();
  const downloads = page.getByRole("link", { name: /Download/ });
  expect(await downloads.count()).toBeGreaterThan(0);
  const href = await downloads.first().getAttribute("href");
  expect(href).toMatch(/^\/exports\/.+/);
  const response = await page.request.get(href!);
  expect(response.status()).toBe(200);
  expect((await response.body()).byteLength).toBeGreaterThan(0);
});
