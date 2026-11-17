import { describe, expect, it, vi } from "vitest";
import { getStaffAccess, isPlatformAdmin, mayManageIngestion } from "../staff-access";

function client(role: string | null, error: unknown = null, userId = "user-id") {
  return { from: vi.fn(() => ({ select: vi.fn(() => ({ eq: vi.fn(() => ({ maybeSingle: vi.fn(async () => ({
    data: role ? { id: userId, role } : null, error,
  })) })) })) })) };
}

describe("staff access lookup", () => {
  it("grants upload access only to the administrator", async () => {
    const access = await getStaffAccess(client("admin"), "user-id");
    expect(access).toMatchObject({ status: "verified", role: "admin", canUpload: true });
    expect(await mayManageIngestion(client("admin"), "user-id")).toBe(true);
    expect(await isPlatformAdmin(client("admin"), "user-id")).toBe(true);
  });

  it("verifies viewer but does not grant upload access", async () => {
    expect(await getStaffAccess(client("viewer"), "user-id")).toMatchObject({
      status: "verified", role: "viewer", canUpload: false,
    });
    expect(await mayManageIngestion(client("viewer"), "user-id")).toBe(false);
  });

  it("distinguishes a missing profile, a lookup failure, and an invalid role", async () => {
    expect(await getStaffAccess(client(null), "user-id")).toMatchObject({ status: "profile_missing", canUpload: false });
    expect(await getStaffAccess(client(null, new Error("RLS denied")), "user-id")).toMatchObject({ status: "lookup_failed", canUpload: false });
    expect(await getStaffAccess(client("root"), "user-id")).toMatchObject({ status: "invalid_role", canUpload: false });
    expect(await getStaffAccess(client("analyst"), "user-id")).toMatchObject({ status: "invalid_role", canUpload: false });
    expect(await getStaffAccess(client("scout"), "user-id")).toMatchObject({ status: "invalid_role", canUpload: false });
    expect(await getStaffAccess(client("analyst", null, "another-user"), "user-id")).toMatchObject({ status: "profile_missing", canUpload: false });
    expect(await mayManageIngestion(client(null, new Error("lookup failed")), "user-id")).toBe(false);
  });
});

describe("isPlatformAdmin", () => {
  it("allows only a verified administrator profile", async () => {
    expect(await isPlatformAdmin(client("admin"), "user-id")).toBe(true);
    expect(await isPlatformAdmin(client("scout"), "user-id")).toBe(false);
    expect(await isPlatformAdmin(client("viewer"), "user-id")).toBe(false);
    expect(await isPlatformAdmin(client(null), "user-id")).toBe(false);
    expect(await isPlatformAdmin(client(null, new Error("lookup failed")), "user-id")).toBe(false);
  });
});
