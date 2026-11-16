"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createBrowserClient } from "@supabase/ssr";
import { CircleAlert, LogIn } from "lucide-react";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  const configured = Boolean(url && key);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  async function signIn(mode: "password" | "magic") {
    if (!configured) return;
    setBusy(true);
    setError(null);
    const supabase = createBrowserClient(url!, key!);
    const redirectTo = `${process.env.NEXT_PUBLIC_APP_URL ?? window.location.origin}${params.get("next") ?? "/"}`;
    const result =
      mode === "password"
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signInWithOtp({ email, options: { emailRedirectTo: redirectTo } });
    setBusy(false);
    if (result.error) {
      setError(result.error.message);
      return;
    }
    if (mode === "magic") setSent(true);
    else {
      router.push(params.get("next") ?? "/");
      router.refresh();
    }
  }

  return (
    <div className="mx-auto max-w-md py-10">
      <div className="rounded-lg border border-surface-line bg-surface p-6 shadow-card">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded bg-royal-pink font-mono text-sm font-bold text-white">RS</div>
          <div>
            <h1 className="text-sm font-semibold text-ink">Royal Scout Intelligence Hub</h1>
            <p className="text-2xs text-ink-faint">Scouting access is restricted to authorised staff</p>
          </div>
        </div>

        {!configured ? (
          <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs leading-relaxed text-amber-900">
            <p className="flex items-center gap-1.5 font-medium"><CircleAlert className="h-3.5 w-3.5" /> Authentication is not configured</p>
            <p className="mt-1">
              Production access is locked until authentication is configured. Set{" "}
              <code className="font-mono">NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
              <code className="font-mono">NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY</code> in Vercel, then create an authorised
              staff account in Supabase Auth. Local development can still preview the read-only snapshot.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <label className="block text-2xs font-medium tracking-wide text-ink-faint uppercase">
              Email
              <input className="input mt-1 w-full" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
            </label>
            <label className="block text-2xs font-medium tracking-wide text-ink-faint uppercase">
              Password
              <input className="input mt-1 w-full" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
            </label>
            {error ? <p className="rounded border border-rose-200 bg-rose-50 px-2 py-1.5 text-2xs text-rose-800">{error}</p> : null}
            {sent ? <p className="rounded border border-emerald-200 bg-emerald-50 px-2 py-1.5 text-2xs text-emerald-800">Magic link sent — check your inbox.</p> : null}
            <div className="flex gap-2">
              <button className="btn-primary flex-1 justify-center" disabled={busy || !email || !password} onClick={() => signIn("password")}>
                <LogIn className="h-3.5 w-3.5" /> Sign in
              </button>
              <button className="btn" disabled={busy || !email} onClick={() => signIn("magic")}>
                Email link
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-md py-10 text-xs text-ink-faint">Loading…</div>}>
      <LoginForm />
    </Suspense>
  );
}
