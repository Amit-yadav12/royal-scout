import { describe, expect, it } from "vitest";
import { buildCsv } from "../csv-provenance";

describe("CSV export", () => {
  it("quotes separators, quotes and newlines", () => {
    const csv = buildCsv(["a", "b"], [["plain", 'has "quotes"'], ["comma,inside", "line\nbreak"]]);
    expect(csv).toContain('"has ""quotes"""');
    expect(csv).toContain('"comma,inside"');
    expect(csv).toContain('"line\nbreak"');
  });

  const body = (csv: string) => csv.split("\n").filter((l) => !l.startsWith("#"));

  it("renders missing values as an empty cell, not as zero", () => {
    expect(body(buildCsv(["x"], [[null]]))).toEqual(["x", ""]);
  });

  it("writes a provenance header block before the table", () => {
    const csv = buildCsv(["x"], [[1]], { dataset: "Demo", model_version: "1.0.0" });
    expect(csv.startsWith("#")).toBe(true);
    expect(csv).toContain("# dataset: Demo");
    expect(csv).toContain("# model_version: 1.0.0");
    expect(csv).toContain("# calculated_at:");
    expect(body(csv)).toEqual(["x", "1"]);
  });

  it("never emits a header-only file when rows exist", () => {
    const csv = buildCsv(["a"], [[1], [2]]);
    expect(body(csv)).toHaveLength(3);
  });
});
