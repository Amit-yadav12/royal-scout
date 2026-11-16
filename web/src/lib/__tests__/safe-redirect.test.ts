import { describe, expect, it } from "vitest";
import { safeRedirectTarget } from "../safe-redirect";

describe("safeRedirectTarget", () => {
  it("preserves a local path, query, and fragment", () => {
    expect(safeRedirectTarget("/players/A%20Player?tab=pressure#evidence")).toBe("/players/A%20Player?tab=pressure#evidence");
  });

  it.each(["https://evil.example", "//evil.example/path", "javascript:alert(1)", "\\\\evil.example", "/\\\\evil.example", "/path\nheader"]) (
    "rejects unsafe target %s", (target) => {
      expect(safeRedirectTarget(target)).toBe("/");
    },
  );

  it("uses the supplied safe fallback", () => {
    expect(safeRedirectTarget(null, "/overview")).toBe("/overview");
  });
});
