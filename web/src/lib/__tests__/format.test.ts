import { describe, expect, it } from "vitest";
import { bytes, dec, num, pct, scoreTone, shortDate, titleCase } from "../format";

describe("format helpers", () => {
  it("renders missing values as an em dash, never as zero", () => {
    expect(num(null)).toBe("—");
    expect(num(undefined)).toBe("—");
    expect(dec(null)).toBe("—");
    expect(pct(null)).toBe("—");
    // missing != zero: zero must still render as a number
    expect(num(0)).toBe("0");
    expect(pct(0)).toBe("0.0%");
  });

  it("formats cricket figures with fixed precision", () => {
    expect(dec(45.678, 1)).toBe("45.7");
    expect(pct(60.25, 1)).toBe("60.3%");
    expect(num(3840)).toBe("3,840");
  });

  it("never renders NaN", () => {
    expect(num(Number.NaN)).toBe("—");
    expect(dec(Number.NaN)).toBe("—");
  });

  it("formats byte sizes", () => {
    expect(bytes(0)).toBe("0 B");
    expect(bytes(512)).toBe("512 B");
    expect(bytes(2048)).toBe("2.0 KB");
    expect(bytes(33_959)).toBe("33 KB");
  });

  it("formats dates in UTC so server and client agree", () => {
    expect(shortDate("2026-02-01T10:30:00Z")).toBe("01 Feb 2026, 10:30 UTC");
    expect(shortDate(null)).toBe("—");
    expect(shortDate("not-a-date")).toBe("not-a-date");
  });

  it("tones scores monotonically", () => {
    expect(scoreTone(null)).toBe("text-ink-faint");
    expect(scoreTone(85)).toBe("text-emerald-700");
    expect(scoreTone(65)).toBe("text-sky-700");
    expect(scoreTone(45)).toBe("text-amber-700");
    expect(scoreTone(10)).toBe("text-rose-700");
  });

  it("title-cases snake_case labels", () => {
    expect(titleCase("wicket_taking_score")).toBe("Wicket Taking Score");
  });
});
