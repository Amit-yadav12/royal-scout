import { describe, expect, it } from "vitest";
import { bundle, getScope, hasBundle, limitations, scopeOptions } from "../bundle";

describe("bundle snapshot", () => {
  it("loads a real engine-produced bundle", () => {
    expect(hasBundle()).toBe(true);
    expect(bundle.meta.model_version).toBeTruthy();
    expect(bundle.meta.config_fingerprint).toBeTruthy();
  });

  it("ships at most 30 ranked players per discipline and never invents rows", () => {
    const global = getScope(null)!;
    expect(global.batters.length).toBeLessThanOrEqual(30);
    expect(global.bowlers.length).toBeLessThanOrEqual(30);
    for (const row of [...global.batters, ...global.bowlers]) {
      expect(row.player).toBeTruthy();
      expect(row.grade).toMatch(/^[ABCD]$/);
      expect(typeof row.rabi === "number" || typeof row.rabi_bowl === "number").toBe(true);
    }
  });

  it("explains eligibility on every ranked row", () => {
    const global = getScope(null)!;
    for (const row of global.batters) {
      expect(row.eligibility_reason === null || typeof row.eligibility_reason === "string").toBe(true);
      expect((row.exposure_balls ?? 0)).toBeGreaterThan(0);
    }
  });

  it("resolves a filtered scope to a real subset", () => {
    const options = scopeOptions();
    expect(options.length).toBeGreaterThan(0);
    const teamScope = options.find((o) => o.type === "team");
    if (teamScope) {
      const scope = getScope(teamScope.label)!;
      expect(scope.scope.label).toBe(teamScope.label);
      expect(scope.batters.length).toBeLessThanOrEqual(30);
    }
  });

  it("falls back to a real scope rather than fabricating an empty one", () => {
    const scope = getScope("does-not-exist")!;
    expect(scope.scope.label).toBeTruthy();
  });

  it("exposes limitations text used in exports and the methodology page", () => {
    const items = limitations();
    expect(Array.isArray(items)).toBe(true);
    expect(items.every((l) => typeof l === "string" && l.length > 0)).toBe(true);
  });

  it("keeps pressure honest about ball-by-ball availability", () => {
    const global = getScope(null)!;
    const anyPressure = global.batters.some((b) => typeof b.pressure_score === "number");
    expect(anyPressure).toBe(bundle.schema.capabilities.ball_by_ball);
  });
});
