import { describe, expect, it } from "vitest";
import { existingStaffOtpOptions, isAssignableStaffRole } from "../auth-policy";

describe("private staff authentication policy", () => {
  it("requests a magic link only for an existing user", () => {
    expect(existingStaffOtpOptions("https://scout.example/auth/callback")).toEqual({
      shouldCreateUser: false,
      emailRedirectTo: "https://scout.example/auth/callback",
    });
  });

  it("allows only read-only viewer invitations; admin elevation stays bootstrap-only", () => {
    expect(isAssignableStaffRole("viewer")).toBe(true);
    expect(isAssignableStaffRole("analyst")).toBe(false);
    expect(isAssignableStaffRole("scout")).toBe(false);
    expect(isAssignableStaffRole("admin")).toBe(false);
  });

  it.each(["owner", "anonymous", "", null, undefined, 1])("rejects malformed staff role %s", (role) => {
    expect(isAssignableStaffRole(role)).toBe(false);
  });
});
