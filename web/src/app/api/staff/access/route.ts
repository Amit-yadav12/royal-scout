import { NextResponse } from "next/server";
import { createServerSupabase } from "@/lib/supabase";
import { getStaffAccess } from "@/lib/staff-access";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const session = await createServerSupabase();
  if (!session) return NextResponse.json({ status: "lookup_failed", role: null, canUpload: false,
    message: "Supabase authentication is not configured for this deployment." }, { status: 503, headers: { "Cache-Control": "no-store" } });
  const { data: { user }, error } = await session.auth.getUser();
  if (error || !user) return NextResponse.json({ status: "unauthenticated", role: null, canUpload: false,
    message: "Your sign-in session is no longer valid. Sign in again to verify staff access." }, { status: 401, headers: { "Cache-Control": "no-store" } });

  const access = await getStaffAccess(session, user.id);
  const statusCode = access.status === "lookup_failed" ? 503 : access.status === "invalid_role" ? 409 : 200;
  return NextResponse.json(access, { status: statusCode, headers: { "Cache-Control": "no-store" } });
}
