import { describe, expect, it } from "vitest";
import { existingStaffOtpOptions, isAssignableStaffRole } from "../auth-policy";

describe("private staff authentication policy", () => {
  it("requests a magic link only for an existing user", () => {
    expect(existingStaffOtpOptions("https://scout.example/auth/callback")).toEqual({
      shouldCreateUser: false,
      emailRedirectTo: "https://scout.example/auth/callback",
    });
  });

  it.each(["viewer", "analyst", "scout", "admin"])("allows an administrator to assign %s", (role) => {
    expect(isAssignableStaffRole(role)).toBe(true);
  });

  it.each(["owner", "anonymous", "", null, undefined, 1])("rejects malformed staff role %s", (role) => {
    expect(isAssignableStaffRole(role)).toBe(false);
  });
});
