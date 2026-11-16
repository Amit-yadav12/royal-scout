import { describe, expect, it } from "vitest";
import { existingStaffOtpOptions, isInvitableStaffRole } from "../auth-policy";

describe("private staff authentication policy", () => {
  it("requests a magic link only for an existing user", () => {
    expect(existingStaffOtpOptions("https://scout.example/auth/callback")).toEqual({
      shouldCreateUser: false,
      emailRedirectTo: "https://scout.example/auth/callback",
    });
  });

  it.each(["viewer", "analyst", "scout"])("permits administrator invitation of %s staff", (role) => {
    expect(isInvitableStaffRole(role)).toBe(true);
  });

  it.each(["admin", "owner", "anonymous", "", null, undefined, 1])("rejects privileged or malformed invitation role %s", (role) => {
    expect(isInvitableStaffRole(role)).toBe(false);
  });
});
