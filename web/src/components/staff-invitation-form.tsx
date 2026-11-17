"use client";

import { useState } from "react";
import { CheckCircle2, CircleAlert, LoaderCircle, MailPlus, ShieldCheck } from "lucide-react";

type InviteResult = { invited?: boolean; email?: string; role?: string; warning?: string; error?: string };

export function StaffInvitationForm() {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<"viewer" | "analyst" | "scout" | "admin">("viewer");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function invite(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch("/api/admin/invitations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, display_name: name, role }),
      });
      const result = await response.json() as InviteResult;
      if (!response.ok) throw new Error(result.error ?? "The invitation could not be sent.");
      setEmail("");
      setName("");
      setNotice(result.warning ?? `Invitation sent to ${result.email}. Assigned role: ${result.role}.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The invitation could not be sent. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={(event) => void invite(event)} className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-xs font-medium text-ink-soft">Staff email
          <input className="input mt-2 h-10 w-full rounded-lg px-3" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="colleague@club.org" required />
        </label>
        <label className="block text-xs font-medium text-ink-soft">Display name <span className="font-normal text-ink-faint">(optional)</span>
          <input className="input mt-2 h-10 w-full rounded-lg px-3" value={name} onChange={(event) => setName(event.target.value)} maxLength={120} placeholder="Staff member" />
        </label>
      </div>
      <label className="block max-w-sm text-xs font-medium text-ink-soft">Initial access
        <select className="input mt-2 h-10 w-full rounded-lg px-3" value={role} onChange={(event) => setRole(event.target.value as typeof role)}>
          <option value="viewer">Viewer · read-only scouting</option>
          <option value="analyst">Analyst · manage data and jobs</option>
          <option value="scout">Scout · upload and process</option>
          <option value="admin">Administrator · manage staff and data</option>
        </select>
      </label>
      {error ? <p role="alert" className="private-message private-message--error"><CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />{error}</p> : null}
      {notice ? <p role="status" className="private-message private-message--success"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />{notice}</p> : null}
      <div className="flex flex-wrap items-center justify-between gap-4 border-t border-surface-line pt-4">
        <p className="flex max-w-xl items-start gap-2 text-2xs leading-relaxed text-ink-faint"><ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-royal-gold" />Only verified platform admins can choose an initial role. New staff must use the single-use invite link to activate their account.</p>
        <button type="submit" disabled={busy || !email} className="btn-pink h-10 justify-center rounded-lg px-4">
          {busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <MailPlus className="h-4 w-4" />}
          {busy ? "Sending invitation…" : "Send staff invitation"}
        </button>
      </div>
    </form>
  );
}
