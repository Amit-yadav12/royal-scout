import { describe, expect, it } from "vitest";
import { existingAdminOtpOptions } from "../auth-policy";

describe("administrator sign-in policy", () => {
  it("sends a sign-in link only to an existing Auth user", () => {
    expect(existingAdminOtpOptions("https://scout.example/auth/callback")).toEqual({
      shouldCreateUser: false,
      emailRedirectTo: "https://scout.example/auth/callback",
    });
  });
});
