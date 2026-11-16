import { describe, expect, it } from "vitest";
import { DEFAULT_FILTERS, filterRows, rankDelta, sortRows, uniqueValues, withFilteredRanks } from "../filters";
import type { PlayerRow } from "../types";

const row = (over: Partial<PlayerRow>): PlayerRow => ({
  player: "Test Player",
  teams: ["Rajasthan Royals"],
  innings: 10,
  primary_role: "Batter",
  grade: "B",
  rabi: 60,
  exposure_balls: 200,
  ...over,
});

const rows: PlayerRow[] = [
  row({ player: "Alpha", rabi: 90, exposure_balls: 400, teams: ["Rajasthan Royals"], rank: 1 }),
  row({ player: "Bravo", rabi: 70, exposure_balls: 120, teams: ["Mumbai Indians"], grade: "C", rank: 2 }),
  row({ player: "Charlie", rabi: null, exposure_balls: 20, teams: [], grade: "D", rank: 3 }),
];

describe("ranking filters", () => {
  it("filters by search term case-insensitively", () => {
    const out = filterRows(rows, { ...DEFAULT_FILTERS, search: "brav" }, "rabi");
    expect(out.map((r) => r.player)).toEqual(["Bravo"]);
  });

  it("filters by team and role", () => {
    expect(filterRows(rows, { ...DEFAULT_FILTERS, team: "rajasthan royals" }, "rabi")).toHaveLength(1);
    expect(filterRows(rows, { ...DEFAULT_FILTERS, role: "Batter" }, "rabi")).toHaveLength(3);
    expect(filterRows(rows, { ...DEFAULT_FILTERS, role: "Bowler" }, "rabi")).toHaveLength(0);
  });

  it("treats a grade filter as a floor (better or equal only)", () => {
    // Alpha is B, Bravo is C, Charlie is D -> a floor of B keeps only Alpha.
    const out = filterRows(rows, { ...DEFAULT_FILTERS, grade: "B" }, "rabi");
    expect(out.map((r) => r.player)).toEqual(["Alpha"]);
    const floorC = filterRows(rows, { ...DEFAULT_FILTERS, grade: "C" }, "rabi");
    expect(floorC.map((r) => r.player)).toEqual(["Alpha", "Bravo"]);
  });

  it("excludes rows below the minimum exposure", () => {
    const out = filterRows(rows, { ...DEFAULT_FILTERS, minExposure: 150 }, "rabi");
    expect(out.map((r) => r.player)).toEqual(["Alpha"]);
    const wider = filterRows(rows, { ...DEFAULT_FILTERS, minExposure: 100 }, "rabi");
    expect(wider.map((r) => r.player)).toEqual(["Alpha", "Bravo"]);
  });

  it("treats a null score as failing a positive minimum, not as zero-but-eligible", () => {
    const out = filterRows(rows, { ...DEFAULT_FILTERS, minScore: 1 }, "rabi");
    expect(out.map((r) => r.player)).toEqual(["Alpha", "Bravo"]);
  });

  it("sorts descending and keeps missing values last", () => {
    const out = sortRows(rows, "rabi", "desc");
    expect(out.map((r) => r.player)).toEqual(["Alpha", "Bravo", "Charlie"]);
    const asc = sortRows(rows, "rabi", "asc");
    expect(asc.map((r) => r.player)).toEqual(["Bravo", "Alpha", "Charlie"]);
  });

  it("re-ranks a filtered view while preserving the scope rank", () => {
    const filtered = withFilteredRanks(filterRows(rows, { ...DEFAULT_FILTERS, team: "Mumbai Indians" }, "rabi"));
    expect(filtered[0].filtered_rank).toBe(1);
    expect(filtered[0].rank).toBe(2);
    expect(rankDelta(filtered[0])).toBe(1);
  });

  it("collects unique filter values from arrays and scalars", () => {
    expect(uniqueValues(rows, "teams")).toEqual(["Mumbai Indians", "Rajasthan Royals"]);
    expect(uniqueValues(rows, "grade")).toEqual(["B", "C", "D"]);
  });
});
