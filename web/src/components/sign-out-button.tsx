"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createBrowserClient } from "@supabase/ssr";
import { LogOut } from "lucide-react";

export function SignOutButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signOut() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
      const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
      if (!url || !key) throw new Error("Authentication is not configured.");
      const { error } = await createBrowserClient(url, key).auth.signOut();
      if (error) throw error;
      router.replace("/login");
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not sign out. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="flex flex-col items-end gap-1">
    <button className="btn" type="button" onClick={() => void signOut()} disabled={busy} aria-label="Sign out">
      <LogOut className="h-3.5 w-3.5" />{busy ? "Signing out…" : "Sign out"}
    </button>
    {error ? <span role="alert" className="max-w-48 text-2xs text-rose-700">{error}</span> : null}
  </div>;
}
