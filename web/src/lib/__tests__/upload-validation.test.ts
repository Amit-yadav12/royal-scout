import { describe, expect, it } from "vitest";
import { MAX_SINGLE_UPLOAD_BYTES, validateUploadFiles } from "../upload-validation";

describe("upload validation", () => {
  it("accepts supported cricket files including compound tar.gz archives", () => {
    expect(validateUploadFiles([{ name: "season.tar.gz", size: 1200 }, { name: "innings.csv", size: 500 }])).toBeNull();
  });
  it("rejects empty, unsupported, oversized and excessive batches", () => {
    expect(validateUploadFiles([])).toContain("Choose at least one");
    expect(validateUploadFiles([{ name: "run.exe", size: 10 }])).toContain("unsupported");
    expect(validateUploadFiles([{ name: "large.zip", size: MAX_SINGLE_UPLOAD_BYTES + 1 }])).toContain("2 GiB");
    expect(validateUploadFiles(Array.from({ length: 201 }, (_, i) => ({ name: `${i}.csv`, size: 1 })))).toContain("no more than");
  });
  it("rejects empty and invalid byte counts", () => {
    expect(validateUploadFiles([{ name: "zero.csv", size: 0 }])).toContain("empty");
    expect(validateUploadFiles([{ name: "bad.csv", size: Number.NaN }])).toContain("invalid size");
  });
});
