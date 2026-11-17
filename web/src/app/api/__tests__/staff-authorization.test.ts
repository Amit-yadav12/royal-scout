import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createServerSupabase: vi.fn(),
  getStaffAccess: vi.fn(),
}));

vi.mock("@/lib/supabase", () => ({ createServerSupabase: mocks.createServerSupabase }));
vi.mock("@/lib/staff-access", () => ({ getStaffAccess: mocks.getStaffAccess }));

import { POST as signUpload } from "../uploads/sign/route";
import { POST as createJob } from "../jobs/route";
import { GET as staffAccess } from "../staff/access/route";

const viewerAccess = {
  status: "verified", role: "viewer", canUpload: false, message: null,
} as const;
const user = { id: "b9929c36-a7c2-4cc1-9293-73758f71e6ec" };

function sameOriginPost(path: string) {
  return new Request(`http://localhost${path}`, {
    method: "POST",
    headers: { Origin: "http://localhost", "Content-Type": "application/json" },
    body: "{}",
  });
}

describe("staff-gated ingestion routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.createServerSupabase.mockResolvedValue({ auth: { getUser: async () => ({ data: { user }, error: null }) } });
    mocks.getStaffAccess.mockResolvedValue(viewerAccess);
    delete process.env.WORKER_API_URL;
    delete process.env.WORKER_SHARED_SECRET;
  });

  it("returns HTTP 403 for a verified viewer at upload signing and job creation", async () => {
    const signResponse = await signUpload(sameOriginPost("/api/uploads/sign"));
    const jobResponse = await createJob(sameOriginPost("/api/jobs"));
    expect(signResponse.status).toBe(403);
    expect(jobResponse.status).toBe(403);
    expect(mocks.getStaffAccess).toHaveBeenCalledWith(expect.anything(), user.id);
    expect((await signResponse.json()).access_status).toBe("verified");
    expect((await jobResponse.json()).stage).toContain("staff permission");
  });

  it.each(["analyst", "scout"])("fails closed for legacy %s roles", async (legacyRole) => {
    mocks.getStaffAccess.mockResolvedValue({
      status: "invalid_role", role: null, canUpload: false,
      message: `Legacy ${legacyRole} access is no longer supported.`,
    });
    const signResponse = await signUpload(sameOriginPost("/api/uploads/sign"));
    const jobResponse = await createJob(sameOriginPost("/api/jobs"));
    expect(signResponse.status).toBe(403);
    expect(jobResponse.status).toBe(403);
  });

  it("reports a missing profile to the signed-in user without granting access", async () => {
    mocks.getStaffAccess.mockResolvedValue({
      status: "profile_missing", role: null, canUpload: false,
      message: "Profile row is missing.",
    });
    const response = await staffAccess();
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ status: "profile_missing", role: null, canUpload: false });
  });
});
