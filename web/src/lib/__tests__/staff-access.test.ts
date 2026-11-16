import { describe, expect, it, vi } from "vitest";
import { mayManageIngestion } from "../staff-access";

function client(role: string | null, error: unknown = null) {
  return { from: vi.fn(() => ({ select: vi.fn(() => ({ eq: vi.fn(() => ({ maybeSingle: vi.fn(async () => ({ data: role ? { role } : null, error })) })) })) })) };
}

describe("mayManageIngestion", () => {
  it.each(["analyst", "scout", "admin"])("allows the %s role", async (role) => {
    expect(await mayManageIngestion(client(role), "user-id")).toBe(true);
  });

  it("does not allow viewer, missing profiles, or lookup failures", async () => {
    expect(await mayManageIngestion(client("viewer"), "user-id")).toBe(false);
    expect(await mayManageIngestion(client(null), "user-id")).toBe(false);
    expect(await mayManageIngestion(client(null, new Error("lookup failed")), "user-id")).toBe(false);
  });
});
