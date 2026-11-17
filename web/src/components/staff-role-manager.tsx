"use client";

import { useEffect, useState } from "react";
import { CircleAlert, CircleCheck, LoaderCircle, RefreshCw, ShieldCheck } from "lucide-react";

type Staff = { id: string; email: string | null; display_name: string | null; role: "viewer" | "analyst" | "scout" | "admin" };

export function StaffRoleManager({ currentUserId }: { currentUserId: string }) {
  const [staff, setStaff] = useState<Staff[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function load() {
    setLoading(true); setError(null);
    try {
      const response = await fetch("/api/admin/staff", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error ?? "Could not load staff roles.");
      setStaff(Array.isArray(data.staff) ? data.staff : []);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load staff roles."); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);

  async function update(userId: string, role: Staff["role"]) {
    setBusyId(userId); setError(null); setNotice(null);
    try {
      const response = await fetch("/api/admin/staff", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: userId, role }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error ?? "Role update failed.");
      setStaff((current) => current.map((item) => item.id === userId ? data.staff : item));
      setNotice(`Updated ${data.staff.email ?? "staff member"} to ${data.staff.role}.`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Role update failed; the previous role remains unchanged."); }
    finally { setBusyId(null); }
  }

  return <div className="space-y-3">
    <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs text-ink-soft">Only verified admins can grant viewer, analyst, scout, or admin access. You cannot change your own role, and the last admin cannot be downgraded.</p><button type="button" className="btn" onClick={() => void load()} disabled={loading}><RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />Refresh</button></div>
    {error ? <p role="alert" className="private-message private-message--error"><CircleAlert className="h-4 w-4" />{error}</p> : null}
    {notice ? <p role="status" className="private-message private-message--success"><CircleCheck className="h-4 w-4" />{notice}</p> : null}
    {loading ? <p className="flex items-center gap-2 py-5 text-xs text-ink-soft"><LoaderCircle className="h-4 w-4 animate-spin" />Loading staff roles…</p> : staff.length ? <ul className="divide-y divide-surface-line rounded-lg border border-surface-line">
      {staff.map((member) => <li key={member.id} className="flex flex-wrap items-center gap-3 px-3 py-2.5">
        <div className="min-w-0 flex-1"><p className="truncate text-xs font-medium text-ink">{member.display_name || member.email || member.id}</p><p className="truncate text-2xs text-ink-faint">{member.email || member.id}{member.id === currentUserId ? " · you" : ""}</p></div>
        <label className="sr-only" htmlFor={`role-${member.id}`}>Role for {member.email || member.id}</label>
        <select id={`role-${member.id}`} className="input w-40" value={member.role} disabled={member.id === currentUserId || busyId === member.id} onChange={(event) => void update(member.id, event.target.value as Staff["role"])}>
          <option value="viewer">Viewer</option><option value="analyst">Analyst · upload</option><option value="scout">Scout · upload</option><option value="admin">Administrator</option>
        </select>
        {busyId === member.id ? <LoaderCircle className="h-4 w-4 animate-spin text-royal-pink" /> : member.role === "admin" ? <ShieldCheck className="h-4 w-4 text-royal-gold" aria-label="Administrator" /> : null}
      </li>)}
    </ul> : <p className="rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">No staff profiles were returned. Complete the one-time administrator bootstrap procedure before inviting staff.</p>}
  </div>;
}
