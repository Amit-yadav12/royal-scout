"use client";

import { Suspense, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createBrowserClient } from "@supabase/ssr";
import { ArrowRight, CircleAlert, KeyRound, LoaderCircle, LockKeyhole, Mail, ShieldCheck } from "lucide-react";
import { BrandLockup } from "@/components/brand-mark";
import { existingAdminOtpOptions } from "@/lib/auth-policy";

const ADMIN_LOGIN_EMAIL = "amiatyadav1275a@gmail.com";
import { safeRedirectTarget } from "@/lib/safe-redirect";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = useMemo(() => safeRedirectTarget(params.get("next")), [params]);
  const recovery = params.get("recovery") === "1";
  const configured = Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY);
  const email = ADMIN_LOGIN_EMAIL;
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(params.get("auth_error") ? "That secure link is invalid or expired. Request a new link and try again." : null);
  const [notice, setNotice] = useState<string | null>(null);

  function client() {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
    if (!url || !key) throw new Error("Sign-in is not configured for this deployment. Contact the Royal Scout administrator.");
    return createBrowserClient(url, key);
  }
  async function run(label: string, task: () => Promise<void>) {
    setBusy(label); setError(null); setNotice(null);
    try { await task(); }
    catch (cause) {
      const message = cause instanceof Error ? cause.message.toLowerCase() : "";
      if (message.includes("invalid login credentials")) setError("Those details did not match the administrator account. Check the password and try again.");
      else if (message.includes("rate limit") || message.includes("too many")) setError("Too many attempts. Wait a few minutes, then try again.");
      else setError(cause instanceof Error ? cause.message : "Sign-in failed. Check your connection and try again.");
    } finally { setBusy(null); }
  }
  async function signIn(mode: "password" | "magic") {
    await run(mode, async () => {
      const supabase = client();
      const callback = new URL("/auth/callback", window.location.origin);
      callback.searchParams.set("next", next);
      if (mode === "password") {
        const { error: authError } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
        if (authError) throw authError;
        router.replace(next); router.refresh();
      } else {
        const { error: authError } = await supabase.auth.signInWithOtp({ email: email.trim(), options: existingAdminOtpOptions(callback.toString()) });
        if (authError) throw authError;
        setNotice("If this is the administrator account, a secure sign-in link is on its way.");
      }
    });
  }
  async function sendRecovery() {
    await run("recovery", async () => {
      const callback = new URL("/auth/callback", window.location.origin);
      callback.searchParams.set("next", "/login?recovery=1");
      const { error: authError } = await client().auth.resetPasswordForEmail(email.trim(), { redirectTo: callback.toString() });
      if (authError) throw authError;
      setNotice("If this is the administrator account, a password reset link has been sent.");
    });
  }
  async function updatePassword() {
    await run("update", async () => {
      if (newPassword.length < 10) throw new Error("Use at least 10 characters for your new password.");
      const { error: authError } = await client().auth.updateUser({ password: newPassword });
      if (authError) throw authError;
      setNotice("Password updated."); router.replace(next); router.refresh();
    });
  }

  return <main className="private-entry min-h-screen px-4 py-6 text-white sm:px-8 lg:px-12">
    <div className="private-entry__grid" aria-hidden="true" />
    <div className="relative mx-auto flex min-h-[calc(100svh-3rem)] w-full max-w-6xl flex-col">
      <header className="py-2"><BrandLockup /></header>
      <div className="grid flex-1 items-center gap-10 py-10 lg:grid-cols-[1fr_minmax(360px,440px)] lg:gap-16">
        <section className="motion-enter max-w-2xl" aria-label="Royal Scout administrator sign-in">
          <p className="text-xs font-semibold tracking-[0.2em] text-gold-300 uppercase">Administrator access · secure workspace</p>
          <h1 className="mt-6 font-serif text-4xl leading-tight sm:text-6xl">Find the edge.<br /><span className="rose-metal">Know the player.</span></h1>
          <p className="mt-6 max-w-xl text-sm leading-7 text-slate-300/75">The dashboard and analytics are public. Sign in only to upload or process data; those actions require the administrator account.</p>
          <p className="mt-8 border-l border-gold-400/60 pl-4 text-sm font-semibold tracking-[0.15em] text-white/85">ADMINISTRATOR SIGN-IN — PUBLIC DASHBOARD NEEDS NO ACCOUNT</p>
        </section>
        <section className="private-card motion-enter motion-enter--delay rounded-2xl p-5 sm:p-7" aria-labelledby="login-title">
          <div className="mb-6 flex items-center gap-3"><div className="private-card__icon grid h-11 w-11 place-items-center rounded-xl"><LockKeyhole className="h-5 w-5" /></div><div><p className="text-[0.62rem] font-semibold tracking-[0.2em] text-gold-300 uppercase">Administrator only</p><h2 id="login-title" className="font-serif text-2xl">{recovery ? "Restore admin access" : "Administrator sign in"}</h2></div></div>
          {!configured ? <div role="status" className="private-message private-message--error"><CircleAlert className="h-4 w-4" />Authentication is not configured for this deployment. Contact your Royal Scout administrator.</div> : <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); void (recovery ? updatePassword() : signIn("password")); }}>
            {recovery ? <label className="private-label block">New password<input className="private-input mt-2 w-full" type="password" autoComplete="new-password" minLength={10} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required /></label> : <>
              <label className="private-label block">Administrator email<span className="private-input-wrap mt-2 flex items-center gap-2"><Mail className="h-4 w-4 text-gold-300" /><input className="private-input w-full" type="email" autoComplete="username" value={email} readOnly aria-readonly="true" /></span></label>
              <label className="private-label block">Password<span className="private-input-wrap mt-2 flex items-center gap-2"><KeyRound className="h-4 w-4 text-gold-300" /><input className="private-input w-full" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></span></label>
            </>}
            {error ? <p className="private-message private-message--error" role="alert">{error}</p> : null}
            {notice ? <p className="private-message private-message--success" role="status">{notice}</p> : null}
            <button className="private-submit w-full" type="submit" disabled={Boolean(busy) || (recovery ? newPassword.length < 10 : !email || !password)}>{busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <LockKeyhole className="h-4 w-4" />}{busy ? "Working securely…" : recovery ? "Update password" : "Sign in as administrator"}<ArrowRight className="ml-auto h-4 w-4" /></button>
            {!recovery ? <div className="flex flex-wrap justify-between gap-2 border-t border-white/10 pt-3"><button type="button" className="private-text-button" disabled={Boolean(busy) || !email} onClick={() => void signIn("magic")}><Mail className="h-3.5 w-3.5" />Email admin sign-in link</button><button type="button" className="private-text-button" disabled={Boolean(busy) || !email} onClick={() => void sendRecovery()}><KeyRound className="h-3.5 w-3.5" />Reset password</button></div> : null}
          </form>}
          <p className="mt-5 flex items-center gap-2 border-t border-white/10 pt-4 text-xs text-white/50"><ShieldCheck className="h-4 w-4 text-gold-300" />Public pages need no account. Administrator access is verified from the protected Supabase profile, not from email alone.</p>
        </section>
      </div>
      <footer className="border-t border-white/10 py-4 text-xs tracking-wide text-white/40">ROYAL SCOUT · PRIVATE RECRUITMENT INTELLIGENCE</footer>
    </div>
  </main>;
}

export default function LoginPage() {
  return <Suspense fallback={<main className="private-entry grid min-h-screen place-items-center text-white">Opening secure sign-in…</main>}><LoginForm /></Suspense>;
}
