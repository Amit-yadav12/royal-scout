import { redirect, notFound } from "next/navigation";
import { UsersRound, ShieldCheck } from "lucide-react";
import { createServerSupabase } from "@/lib/supabase";
import { isPlatformAdmin } from "@/lib/staff-access";
import { StaffInvitationForm } from "@/components/staff-invitation-form";
import { StaffRoleManager } from "@/components/staff-role-manager";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/shell";

export const dynamic = "force-dynamic";

export default async function StaffAdministrationPage() {
  const session = await createServerSupabase();
  if (!session) notFound();
  const { data: { user }, error } = await session.auth.getUser();
  if (error || !user) redirect("/login?next=%2Fstaff");
  if (!(await isPlatformAdmin(session, user.id))) notFound();

  return <div className="motion-enter space-y-4">
    <PageHeader title="Administration" description="Manage read-only accounts. Only your administrator account can access this area, upload data, or run processing jobs." icon={UsersRound} />
    <div className="mx-auto max-w-5xl space-y-4">
      <Card><CardHeader title="Accounts" subtitle="Your account is the sole administrator. Other accounts have read-only access; role elevation is unavailable in the app." /><CardBody><StaffRoleManager currentUserId={user.id} /></CardBody></Card>
      <Card><CardHeader title="Invite read-only users" subtitle="Invited users can sign in to read analytics, but cannot upload, process, or manage access." /><CardBody><StaffInvitationForm /></CardBody></Card>
      <div className="flex items-start gap-3 rounded-xl border border-gold-400/20 bg-gold-400/[0.06] px-4 py-3 text-xs leading-relaxed text-ink-soft"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-royal-gold" /><p>Every upload, job submission, and retry is checked server-side and requires the administrator role. The one-time Supabase bootstrap is the only app-supported path to create the admin; email domains never grant privileges.</p></div>
    </div>
  </div>;
}
