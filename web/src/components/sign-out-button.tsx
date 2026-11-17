"use client";

import { useState } from "react";
import Link from "next/link";
import { createBrowserClient } from "@supabase/ssr";

export function SignOutButton({ authenticated }: { authenticated: boolean }) {
  const [busy, setBusy] = useState(false);
  if (!authenticated) return <Link className="btn" href="/login">Sign in</Link>;

  async function signOut() {
    setBusy(true);
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
    if (!url || !key) {
      setBusy(false);
      return;
    }
    const supabase = createBrowserClient(url, key);
    const { error } = await supabase.auth.signOut();
    if (error) {
      setBusy(false);
      window.alert(`Could not sign out: ${error.message}`);
      return;
    }
    window.location.assign("/");
  }

  return <button type="button" className="btn" onClick={signOut} disabled={busy}>
    {busy ? "Signing out…" : "Sign out"}
  </button>;
}
