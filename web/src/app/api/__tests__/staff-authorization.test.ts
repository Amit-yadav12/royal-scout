import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createServerSupabase: vi.fn(),
  getStaffAccess: vi.fn(),
}));

vi.mock("@/lib/supabase", () => ({
  createServerSupabase: mocks.createServerSupabase,
  supabaseServerHeaders: vi.fn(() => ({ apikey: "server-key", "Content-Type": "application/json" })),
}));
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
    expect((await jobResponse.json()).stage).toContain("admin permission");
  });

  it("returns the signed TUS endpoint for an admin-authorized private upload", async () => {
    const previousEnv = {
      SUPABASE_URL: process.env.SUPABASE_URL,
      SUPABASE_SECRET_KEY: process.env.SUPABASE_SECRET_KEY,
      SUPABASE_SERVICE_ROLE_KEY: process.env.SUPABASE_SERVICE_ROLE_KEY,
      ROYAL_SCOUT_PROJECT_ID: process.env.ROYAL_SCOUT_PROJECT_ID,
    };
    process.env.SUPABASE_URL = "https://xncrdfgetktfmnhflltd.supabase.co";
    process.env.SUPABASE_SECRET_KEY = "sb_secret_test";
    delete process.env.SUPABASE_SERVICE_ROLE_KEY;
    process.env.ROYAL_SCOUT_PROJECT_ID = "royal-scout";
    mocks.getStaffAccess.mockResolvedValue({
      status: "verified", role: "admin", canUpload: true, message: null,
    });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const target = String(input);
      if (target.includes("/storage/v1/object/upload/sign/")) {
        return new Response(JSON.stringify({ token: "signed-upload-token", url: "/object/upload/sign/uploads/example" }), {
          status: 200, headers: { "Content-Type": "application/json" },
        });
      }
      if (target.includes("/rest/v1/upload_claims")) return new Response(null, { status: 201 });
      return new Response(null, { status: 404 });
    });

    try {
      const request = new Request("http://localhost/api/uploads/sign", {
        method: "POST",
        headers: { Origin: "http://localhost", "Content-Type": "application/json" },
        body: JSON.stringify({ dataset_name: "Test dataset", files: [{ name: "data.csv", size: 10, type: "text/csv" }] }),
      });
      const response = await signUpload(request);
      const payload = await response.json();
      expect(response.status, JSON.stringify(payload)).toBe(200);
      expect(payload.files[0].tus_endpoint).toBe(
        "https://xncrdfgetktfmnhflltd.storage.supabase.co/storage/v1/upload/resumable/sign",
      );
      expect(fetchMock).toHaveBeenCalledTimes(2);
    } finally {
      fetchMock.mockRestore();
      for (const [key, value] of Object.entries(previousEnv)) {
        if (value === undefined) delete process.env[key];
        else process.env[key] = value;
      }
    }
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
