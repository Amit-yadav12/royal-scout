"use client";

import { useEffect, useState } from "react";
import { CircleAlert, LoaderCircle, RefreshCw, ShieldCheck } from "lucide-react";

type Staff = { id: string; email: string | null; display_name: string | null; role: "viewer" | "admin" };

export function StaffRoleManager({ currentUserId }: { currentUserId: string }) {
  const [staff, setStaff] = useState<Staff[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/admin/staff", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error ?? "Could not load accounts.");
      setStaff(Array.isArray(data.staff) ? data.staff : []);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load accounts.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  return <div className="space-y-3">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="text-xs text-ink-soft">There is one administrator. All other invited accounts are read-only; administrator access cannot be assigned here.</p>
      <button type="button" className="btn" onClick={() => void load()} disabled={loading}>
        <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />Refresh
      </button>
    </div>
    {error ? <p role="alert" className="private-message private-message--error"><CircleAlert className="h-4 w-4" />{error}</p> : null}
    {loading ? <p className="flex items-center gap-2 py-5 text-xs text-ink-soft"><LoaderCircle className="h-4 w-4 animate-spin" />Loading accounts…</p> : staff.length ? <ul className="divide-y divide-surface-line rounded-lg border border-surface-line">
      {staff.map((member) => <li key={member.id} className="flex flex-wrap items-center gap-3 px-3 py-2.5">
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium text-ink">{member.display_name || member.email || member.id}</p>
          <p className="truncate text-2xs text-ink-faint">{member.email || member.id}{member.id === currentUserId ? " · you" : ""}</p>
        </div>
        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-2xs font-medium ${member.role === "admin" ? "bg-gold-400/[0.12] text-royal-gold" : "bg-surface-muted text-ink-soft"}`}>
          {member.role === "admin" ? <ShieldCheck className="h-3 w-3" /> : null}
          {member.role === "admin" ? "Administrator" : "Read-only"}
        </span>
      </li>)}
    </ul> : <p className="rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">No account profiles were returned. Verify profile provisioning in Supabase.</p>}
  </div>;
}
