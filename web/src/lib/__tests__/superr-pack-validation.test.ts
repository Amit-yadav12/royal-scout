import { describe, expect, it } from "vitest";
import { isIncompleteSuperrPackError, validateSuperrPackHeaders } from "../superr-pack-validation";

const headers = [
  { name: "delivery.csv", header: "match_id,innings,overid,over_ball_num,striker_id,bowler_id" },
  { name: "matches.csv", header: "match_id,comp_id,match_date,result" },
  { name: "competitions.csv", header: "comp_id,comp_name,match_format,season" },
  { name: "xi.csv", header: "match_id,player_id,is_played,batting_order" },
  { name: "mapping.csv", header: "comp_id,team_id,player_id,player_name" },
];

describe("SupeRR upload preflight", () => {
  it("accepts all required tables by schema even when filenames differ", () => {
    expect(validateSuperrPackHeaders(headers)).toBeNull();
  });

  it("reports missing tables before a partial ball-by-ball pack is uploaded", () => {
    const message = validateSuperrPackHeaders([headers[0], headers[2], headers[3]]);
    expect(message).toContain("missing required tables: matches, competition/player mapping");
    expect(message).toContain("Files from earlier uploads are not combined");
  });

  it("does not impose SupeRR requirements on unrelated cricket CSVs", () => {
    expect(validateSuperrPackHeaders([{ name: "batting.csv", header: "player,runs,balls" }])).toBeNull();
  });

  it("leaves archives to the server-side nested archive detector", () => {
    expect(validateSuperrPackHeaders([headers[0]], true)).toBeNull();
  });

  it("recognises a terminal incomplete-pack error", () => {
    expect(isIncompleteSuperrPackError("FileNotFoundError: SupeRR pack is missing required table(s): matches")).toBe(true);
    expect(isIncompleteSuperrPackError("ConnectionTimeout: worker unavailable")).toBe(false);
  });
});
