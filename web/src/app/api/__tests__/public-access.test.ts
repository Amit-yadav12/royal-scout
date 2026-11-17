import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getSuccessfulDatasetOptions: vi.fn(),
  loadDashboardDataset: vi.fn(),
}));

vi.mock("@/lib/server-dataset", () => ({
  getSuccessfulDatasetOptions: mocks.getSuccessfulDatasetOptions,
  loadDashboardDataset: mocks.loadDashboardDataset,
}));
vi.mock("@/lib/bundle", () => ({
  getScope: () => ({ scope: { label: "global" }, batters: [], bowlers: [] }),
  hasBundle: () => true,
}));
vi.mock("@/lib/csv-provenance", () => ({ buildCsv: () => "public,csv\n" }));

import { POST as selectDataset } from "../datasets/active/route";
import { GET as exportCsv } from "../export/route";

const publicBundle = {
  meta: {
    name: "Public data", dataset_id: "ds_public", dataset_version: 1,
    model_version: "1.0.0", config_fingerprint: "fingerprint", is_fixture: false,
    limitations: [],
  },
};

describe("public analytics access", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.loadDashboardDataset.mockResolvedValue({ bundle: publicBundle });
    mocks.getSuccessfulDatasetOptions.mockResolvedValue([{ dataset_id: "ds_public" }]);
  });

  it("serves CSV exports without an authenticated session", async () => {
    const response = await exportCsv(new Request("https://royal-scout.example/api/export?discipline=batting"));
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("text/csv");
    expect(await response.text()).toContain("public,csv");
  });

  it("allows an anonymous visitor to select a validated public dataset", async () => {
    const response = await selectDataset(new Request("https://royal-scout.example/api/datasets/active", {
      method: "POST",
      headers: { Origin: "https://royal-scout.example", "Content-Type": "application/json" },
      body: JSON.stringify({ dataset_id: "ds_public" }),
    }));
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ selected_id: "ds_public" });
  });
});
