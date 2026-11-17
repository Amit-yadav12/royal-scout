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
    <PageHeader title="Staff access" description="Provision invited colleagues and manage least-privilege roles. Only authorised administrators can grant analyst/scout upload permissions." icon={UsersRound} />
    <div className="mx-auto max-w-5xl space-y-4">
      <Card><CardHeader title="Current staff roles" subtitle="Viewer is read-only. Analyst and scout can upload and process datasets. Administrator roles cannot be assigned here." /><CardBody><StaffRoleManager currentUserId={user.id} /></CardBody></Card>
      <Card><CardHeader title="Invite staff" subtitle="Public self-registration is disabled. Invitations create authorised accounts with an explicit initial role." /><CardBody><StaffInvitationForm /></CardBody></Card>
      <div className="flex items-start gap-3 rounded-xl border border-gold-400/20 bg-gold-400/[0.06] px-4 py-3 text-xs leading-relaxed text-ink-soft"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-royal-gold" /><p>Role checks are performed on the server for every upload and job request. Initial administrator access is provisioned only through the documented one-time Supabase bootstrap procedure; email domains never grant privileges.</p></div>
    </div>
  </div>;
}
