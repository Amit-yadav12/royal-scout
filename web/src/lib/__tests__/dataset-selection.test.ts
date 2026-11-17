import { describe, expect, it } from "vitest";
import { datasetOptionsFrom, primaryDatasetId, resolveDatasetSelection } from "../dataset-selection";

const successful = [
  { dataset_id: "ds_new", dataset_name: "Newest run", created_at: "2026-11-15T12:00:00Z", finished_at: "2026-11-15T12:04:00Z", is_fixture: false },
  { dataset_id: "ds_old", dataset_name: "Previous run", created_at: "2026-11-10T12:00:00Z", finished_at: "2026-11-10T12:04:00Z", is_fixture: false },
];

describe("dataset history selection", () => {
  it("keeps one successful history entry per dataset and preserves upload creation time", () => {
    expect(datasetOptionsFrom([...successful, successful[0]])).toEqual([
      { dataset_id: "ds_new", name: "Newest run", created_at: "2026-11-15T12:00:00Z", is_fixture: false },
      { dataset_id: "ds_old", name: "Previous run", created_at: "2026-11-10T12:00:00Z", is_fixture: false },
    ]);
  });

  it("defaults to the latest successful upload and preserves explicit dataset selection", () => {
    const options = datasetOptionsFrom(successful);
    expect(primaryDatasetId(options)).toBe("ds_new");
    expect(resolveDatasetSelection(null, options).selectedId).toBe("ds_new");
    expect(resolveDatasetSelection("ds_old", options).selectedId).toBe("ds_old");
  });

  it("keeps a reprocessed dataset's original first-upload date", () => {
    const rerun = { ...successful[0], created_at: "2026-12-01T12:00:00Z", finished_at: "2026-12-01T12:04:00Z" };
    const options = datasetOptionsFrom([rerun, successful[0], successful[1]]);
    expect(options[0].created_at).toBe(successful[0].created_at);
    expect(primaryDatasetId(options)).toBe("ds_new");
  });

  it("does not silently replace a stale selection with another dataset", () => {
    const result = resolveDatasetSelection("ds_removed", datasetOptionsFrom(successful));
    expect(result.selectedId).toBe("ds_removed");
    expect(result.error).toMatch(/no longer in processing history/i);
  });

  it("reports an empty history rather than inventing a dataset", () => {
    expect(resolveDatasetSelection(null, [])).toMatchObject({ selectedId: null, error: expect.any(String) });
  });
});
