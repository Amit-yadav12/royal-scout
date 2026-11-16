import "server-only";
import { createClient } from "@supabase/supabase-js";
import { NextResponse } from "next/server";
import { createServerSupabase } from "@/lib/supabase";
import { isPlatformAdmin } from "@/lib/staff-access";
import { isInvitableStaffRole } from "@/lib/auth-policy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function jsonError(error: string, status: number) {
  return NextResponse.json({ error }, { status, headers: { "Cache-Control": "no-store" } });
}

export async function POST(request: Request) {
  const requestOrigin = request.headers.get("origin");
  let appOrigin: string;
  try {
    appOrigin = new URL(request.url).origin;
  } catch {
    return jsonError("The request origin could not be verified.", 403);
  }
  if (!requestOrigin || requestOrigin !== appOrigin) {
    return jsonError("Cross-origin staff invitations are not allowed.", 403);
  }

  const session = await createServerSupabase();
  if (!session) return jsonError("Staff authentication is not configured.", 503);
  const { data: { user }, error: authError } = await session.auth.getUser();
  if (authError || !user) return jsonError("Sign in with an authorised administrator account.", 401);
  if (!(await isPlatformAdmin(session, user.id))) return jsonError("Only platform administrators may invite staff.", 403);

  let body: { email?: unknown; display_name?: unknown; role?: unknown };
  try {
    body = await request.json();
  } catch {
    return jsonError("Expected a valid JSON invitation request.", 400);
  }
  const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  const displayName = typeof body.display_name === "string" ? body.display_name.trim().slice(0, 120) : "";
  const role = typeof body.role === "string" ? body.role : "viewer";
  if (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return jsonError("Enter a valid staff email address.", 400);
  }
  if (!isInvitableStaffRole(role)) {
    return jsonError("Choose viewer, analyst, or scout. Administrator privileges cannot be assigned through staff invitations.", 400);
  }

  const supabaseUrl = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
  const secret = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supabaseUrl || !secret || secret.startsWith("sb_publishable_")) {
    return jsonError("Private administrator operations are not configured.", 503);
  }

  const redirectTo = new URL("/auth/callback", appOrigin);
  redirectTo.searchParams.set("next", "/login?recovery=1");
  const admin = createClient(supabaseUrl, secret, {
    auth: { autoRefreshToken: false, persistSession: false, detectSessionInUrl: false },
  });

  const { data, error: inviteError } = await admin.auth.admin.inviteUserByEmail(email, {
    redirectTo: redirectTo.toString(),
    data: displayName ? { full_name: displayName } : {},
  });
  if (inviteError || !data.user) {
    return jsonError("The staff invitation could not be sent. Verify the address and existing account status, then try again.", 409);
  }

  const { error: profileError } = await admin.from("profiles").upsert({
    id: data.user.id,
    email,
    display_name: displayName || email.split("@")[0],
    role,
  }, { onConflict: "id" });

  // The Auth invitation is already sent. If the role write fails, preserve the
  // database trigger's least-privilege viewer default instead of retrying or
  // deleting an authorised account; report the downgrade clearly to the admin.
  if (profileError) {
    return NextResponse.json({
      invited: true,
      email,
      role: "viewer",
      warning: "The invitation was sent with the default viewer role; the requested role could not be assigned. Review staff permissions before use.",
    }, { status: 202, headers: { "Cache-Control": "no-store" } });
  }

  return NextResponse.json({ invited: true, email, role }, { status: 201, headers: { "Cache-Control": "no-store" } });
}
