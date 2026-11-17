import "server-only";
import { createClient } from "@supabase/supabase-js";
import { NextResponse } from "next/server";
import { createServerSupabase } from "@/lib/supabase";
import { isPlatformAdmin } from "@/lib/staff-access";
import { isInvitableStaffRole } from "@/lib/auth-policy";
import { isSameOriginRequest } from "@/lib/request-security";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function adminClient() {
  const url = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key || key.startsWith("sb_publishable_")) return null;
  return createClient(url, key, { auth: { autoRefreshToken: false, persistSession: false, detectSessionInUrl: false } });
}

async function authenticatedAdmin() {
  const session = await createServerSupabase();
  if (!session) return { error: NextResponse.json({ error: "Staff authentication is not configured." }, { status: 503 }) };
  const { data: { user }, error } = await session.auth.getUser();
  if (error || !user) return { error: NextResponse.json({ error: "Sign in with an authorised administrator account." }, { status: 401 }) };
  if (!(await isPlatformAdmin(session, user.id))) return { error: NextResponse.json({ error: "Only platform administrators may manage staff roles." }, { status: 403 }) };
  const admin = adminClient();
  if (!admin) return { error: NextResponse.json({ error: "Server-only Supabase administrator credentials are not configured." }, { status: 503 }) };
  return { admin, user };
}

export async function GET() {
  const auth = await authenticatedAdmin();
  if ("error" in auth) return auth.error;
  const profiles = await auth.admin.from("profiles").select("id,email,display_name,role").order("email").limit(1000);
  if (profiles.error) return NextResponse.json({ error: "Could not read staff profiles. Check the profiles table and service-key permissions." }, { status: 503 });
  return NextResponse.json({ staff: profiles.data ?? [] }, { headers: { "Cache-Control": "no-store" } });
}

export async function PATCH(request: Request) {
  if (!isSameOriginRequest(request)) return NextResponse.json({ error: "Cross-origin staff role changes are not allowed." }, { status: 403 });
  const auth = await authenticatedAdmin();
  if ("error" in auth) return auth.error;
  let body: { user_id?: unknown; role?: unknown };
  try { body = await request.json(); }
  catch { return NextResponse.json({ error: "Expected a staff user_id and role." }, { status: 400 }); }
  const userId = typeof body.user_id === "string" ? body.user_id : "";
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(userId)) {
    return NextResponse.json({ error: "Invalid staff user ID." }, { status: 400 });
  }
  if (userId === auth.user.id) return NextResponse.json({ error: "You cannot change your own role. Ask another administrator." }, { status: 409 });
  if (!isInvitableStaffRole(body.role)) return NextResponse.json({ error: "Choose viewer, analyst, or scout. Administrator privileges are bootstrap-only." }, { status: 400 });

  const { data: target, error: targetError } = await auth.admin.auth.admin.getUserById(userId);
  if (targetError || !target.user) return NextResponse.json({ error: "That authenticated staff account was not found." }, { status: 404 });
  const { data: current, error: roleError } = await auth.admin.from("profiles").select("role").eq("id", userId).maybeSingle();
  if (roleError) return NextResponse.json({ error: "Could not verify the current staff role." }, { status: 503 });
  if (!current) return NextResponse.json({ error: "The user profile is missing. Repair profile provisioning before changing access." }, { status: 409 });
  if (current.role === "admin") return NextResponse.json({ error: "Administrator roles cannot be changed through this screen." }, { status: 409 });

  const { data: updated, error: updateError } = await auth.admin.from("profiles").update({ role: body.role })
    .eq("id", userId).select("id,email,display_name,role").maybeSingle();
  if (updateError || !updated) return NextResponse.json({ error: "The role update failed. The previous role remains in effect." }, { status: 503 });
  return NextResponse.json({ staff: updated }, { headers: { "Cache-Control": "no-store" } });
}
