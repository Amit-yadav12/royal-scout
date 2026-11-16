"use client";

import { Suspense, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createBrowserClient } from "@supabase/ssr";
import { CircleAlert, KeyRound, LogIn, Mail, ShieldCheck } from "lucide-react";
import { safeRedirectTarget } from "@/lib/safe-redirect";
import { BrandLockup } from "@/components/brand-mark";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  const configured = Boolean(url && key);
  const next = useMemo(() => safeRedirectTarget(params.get("next")), [params]);
  const recovery = params.get("recovery") === "1";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(params.get("auth_error") === "callback_failed" ? "The secure sign-in link is invalid or expired. Request a new link and try again." : null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function client() {
    if (!url || !key) throw new Error("Authentication is not configured. Contact your Royal Scout administrator.");
    return createBrowserClient(url, key);
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The request could not be completed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function signIn(mode: "password" | "magic") {
    await run(async () => {
      const supabase = client();
      const callbackUrl = new URL("/auth/callback", window.location.origin);
      callbackUrl.searchParams.set("next", next);
      const result = mode === "password"
        ? await supabase.auth.signInWithPassword({ email: email.trim(), password })
        : await supabase.auth.signInWithOtp({ email: email.trim(), options: { shouldCreateUser: false, emailRedirectTo: callbackUrl.toString() } });
      if (result.error) throw result.error;
      if (mode === "magic") {
        setNotice("Sign-in link sent. Check your inbox, then open the link on this device.");
        return;
      }
      router.replace(next);
      router.refresh();
    });
  }

  async function sendReset() {
    await run(async () => {
      const supabase = client();
      const redirectTo = new URL("/auth/callback", window.location.origin);
      redirectTo.searchParams.set("next", "/login?recovery=1");
      const { error: resetError } = await supabase.auth.resetPasswordForEmail(email.trim(), { redirectTo: redirectTo.toString() });
      if (resetError) throw resetError;
      setNotice("If this email belongs to an authorised staff account, a password reset link has been sent.");
    });
  }

  async function updatePassword() {
    await run(async () => {
      if (newPassword.length < 10) throw new Error("Use at least 10 characters for the new password.");
      const { error: updateError } = await client().auth.updateUser({ password: newPassword });
      if (updateError) throw updateError;
      setNotice("Password updated. Your staff session is ready.");
      router.replace(next);
      router.refresh();
    });
  }

  return (
    <main className="min-h-screen bg-surface-muted px-4 py-10 sm:py-16">
      <div className="mx-auto max-w-md">
        <div className="mb-5 flex justify-center">
          <div className="rounded-xl bg-navy-900 px-4 py-3 shadow-card"><BrandLockup /></div>
        </div>
        <section className="rounded-xl border border-surface-line bg-surface p-6 shadow-card sm:p-8" aria-labelledby="login-title">
          <div className="mb-5 flex items-start gap-3">
            <div className="mt-0.5 rounded-lg bg-navy-900 p-2 text-white"><ShieldCheck className="h-4 w-4" /></div>
            <div>
              <h1 id="login-title" className="text-lg font-semibold text-ink">{recovery ? "Set a new password" : "Staff sign in"}</h1>
              <p className="mt-1 text-xs leading-relaxed text-ink-soft">Access is limited to accounts provisioned by an authorised administrator. Public registration is disabled.</p>
            </div>
          </div>

          {!configured ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-3 text-xs leading-relaxed text-amber-900" role="status">
              <p className="flex items-center gap-1.5 font-medium"><CircleAlert className="h-3.5 w-3.5" /> Authentication is not configured</p>
              <p className="mt-1">Production access remains locked. Configure the public Supabase URL and publishable key, then provision staff through Supabase Auth.</p>
            </div>
          ) : (
            <form className="space-y-3" onSubmit={(event) => { event.preventDefault(); void (recovery ? updatePassword() : signIn("password")); }}>
              {recovery ? (
                <label className="block text-xs font-medium text-ink-soft">New password
                  <input className="input mt-1 w-full" type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" minLength={10} required />
                </label>
              ) : <>
                <label className="block text-xs font-medium text-ink-soft">Work email
                  <input className="input mt-1 w-full" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" required />
                </label>
                <label className="block text-xs font-medium text-ink-soft">Password
                  <input className="input mt-1 w-full" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
                </label>
              </>}

              {error ? <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800" role="alert">{error}</p> : null}
              {notice ? <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800" role="status">{notice}</p> : null}

              {recovery ? (
                <button className="btn-primary w-full justify-center" disabled={busy || newPassword.length < 10} type="submit"><KeyRound className="h-3.5 w-3.5" />{busy ? "Updating…" : "Update password"}</button>
              ) : (
                <>
                  <button className="btn-primary w-full justify-center" disabled={busy || !email || !password} type="submit"><LogIn className="h-3.5 w-3.5" />{busy ? "Signing in…" : "Sign in"}</button>
                  <div className="grid grid-cols-2 gap-2">
                    <button className="btn justify-center" disabled={busy || !email} type="button" onClick={() => void signIn("magic")}><Mail className="h-3.5 w-3.5" />Email link</button>
                    <button className="btn justify-center" disabled={busy || !email} type="button" onClick={() => void sendReset()}><KeyRound className="h-3.5 w-3.5" />Reset password</button>
                  </div>
                </>
              )}
            </form>
          )}
        </section>
        <p className="mt-4 text-center text-2xs text-ink-faint">Need access? Contact your organisation’s Royal Scout administrator.</p>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return <Suspense fallback={<main className="min-h-screen bg-surface-muted p-10 text-center text-xs text-ink-faint">Loading secure sign-in…</main>}><LoginForm /></Suspense>;
}
