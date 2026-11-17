import "server-only";
import { createClient } from "@supabase/supabase-js";
import { NextResponse } from "next/server";
import { createServerSupabase } from "@/lib/supabase";
import { isPlatformAdmin } from "@/lib/staff-access";

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
  if (!session) return { error: NextResponse.json({ error: "Admin authentication is not configured." }, { status: 503 }) };
  const { data: { user }, error } = await session.auth.getUser();
  if (error || !user) return { error: NextResponse.json({ error: "Sign in with the administrator account." }, { status: 401 }) };
  if (!(await isPlatformAdmin(session, user.id))) return { error: NextResponse.json({ error: "Only the platform administrator can manage accounts." }, { status: 403 }) };
  const admin = adminClient();
  if (!admin) return { error: NextResponse.json({ error: "Server-only Supabase administrator credentials are not configured." }, { status: 503 }) };
  return { admin };
}

export async function GET() {
  const auth = await authenticatedAdmin();
  if ("error" in auth) return auth.error;
  const profiles = await auth.admin.from("profiles").select("id,email,display_name,role").order("email").limit(1000);
  if (profiles.error) return NextResponse.json({ error: "Could not read account profiles. Check the profiles table and service-key permissions." }, { status: 503 });
  return NextResponse.json({ staff: profiles.data ?? [] }, { headers: { "Cache-Control": "no-store" } });
}
