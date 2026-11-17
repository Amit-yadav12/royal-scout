"use client";

import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { createBrowserClient } from "@supabase/ssr";
import { ArrowRight, CircleAlert, LoaderCircle, LockKeyhole, Mail, ShieldCheck } from "lucide-react";
import { BrandLockup } from "@/components/brand-mark";
import { existingAdminOtpOptions } from "@/lib/auth-policy";
import { safeRedirectTarget } from "@/lib/safe-redirect";

const ADMIN_LOGIN_EMAIL = "amiatyadav1275a@gmail.com";

function LoginForm() {
  const params = useSearchParams();
  const next = useMemo(() => safeRedirectTarget(params.get("next"), "/ingestion"), [params]);
  const configured = Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(params.get("auth_error") ? "That sign-in link is invalid or expired. Request a new one." : null);
  const [notice, setNotice] = useState<string | null>(null);

  async function sendAdminLink() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
      const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
      if (!url || !key) throw new Error("Passwordless sign-in is not configured for this deployment.");

      const callback = new URL("/auth/callback", window.location.origin);
      callback.searchParams.set("next", next);
      const { error: authError } = await createBrowserClient(url, key).auth.signInWithOtp({
        email: ADMIN_LOGIN_EMAIL,
        options: existingAdminOtpOptions(callback.toString()),
      });
      if (authError) throw authError;
      setNotice(`Check ${ADMIN_LOGIN_EMAIL} for your secure sign-in link. It can be used once and expires shortly.`);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Could not request the sign-in link.";
      const lower = message.toLowerCase();
      if (lower.includes("rate limit") || lower.includes("too many")) {
        setError("Too many email requests. Wait a few minutes and try again.");
      } else if (lower.includes("redirect") && lower.includes("allow")) {
        setError("This app URL is not on Supabase’s allowed redirect list. Add the deployed app URL in Authentication → URL Configuration.");
      } else {
        setError(`${message} If no email arrives, ask the owner to check Supabase Auth SMTP settings and logs.`);
      }
    } finally {
      setBusy(false);
    }
  }

  return <main className="private-entry min-h-screen px-4 py-6 text-white sm:px-8 lg:px-12">
    <div className="private-entry__grid" aria-hidden="true" />
    <div className="relative mx-auto flex min-h-[calc(100svh-3rem)] w-full max-w-6xl flex-col">
      <header className="py-2"><BrandLockup /></header>
      <div className="grid flex-1 items-center gap-10 py-10 lg:grid-cols-[1fr_minmax(360px,440px)] lg:gap-16">
        <section className="motion-enter max-w-2xl" aria-label="Royal Scout administrator sign-in">
          <p className="text-xs font-semibold tracking-[0.2em] text-gold-300 uppercase">Administrator access · passwordless</p>
          <h1 className="mt-6 font-serif text-4xl leading-tight sm:text-6xl">Find the edge.<br /><span className="rose-metal">Know the player.</span></h1>
          <p className="mt-6 max-w-xl text-sm leading-7 text-slate-300/75">The dashboard and analytics are public. Only data upload and processing require the administrator’s secure email link.</p>
          <p className="mt-8 border-l border-gold-400/60 pl-4 text-sm font-semibold tracking-[0.15em] text-white/85">PUBLIC DASHBOARD — ADMIN ACCESS BY EMAIL LINK</p>
        </section>
        <section className="private-card motion-enter motion-enter--delay rounded-2xl p-5 sm:p-7" aria-labelledby="login-title">
          <div className="mb-6 flex items-center gap-3"><div className="private-card__icon grid h-11 w-11 place-items-center rounded-xl"><LockKeyhole className="h-5 w-5" /></div><div><p className="text-[0.62rem] font-semibold tracking-[0.2em] text-gold-300 uppercase">Administrator only</p><h2 id="login-title" className="font-serif text-2xl">Get a sign-in link</h2></div></div>
          {!configured ? <div role="status" className="private-message private-message--error"><CircleAlert className="h-4 w-4" />Passwordless sign-in is not configured for this deployment. Contact the Royal Scout administrator.</div> : <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); void sendAdminLink(); }}>
            <label className="private-label block">Administrator email<span className="private-input-wrap mt-2 flex items-center gap-2"><Mail className="h-4 w-4 text-gold-300" /><input className="private-input w-full" type="email" autoComplete="username" value={ADMIN_LOGIN_EMAIL} readOnly aria-readonly="true" /></span></label>
            {error ? <p className="private-message private-message--error" role="alert">{error}</p> : null}
            {notice ? <p className="private-message private-message--success" role="status">{notice}</p> : null}
            <button className="private-submit w-full" type="submit" disabled={busy || !configured}>{busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}{busy ? "Sending secure link…" : "Email me a sign-in link"}<ArrowRight className="ml-auto h-4 w-4" /></button>
          </form>}
          <p className="mt-5 flex items-center gap-2 border-t border-white/10 pt-4 text-xs text-white/50"><ShieldCheck className="h-4 w-4 text-gold-300" />No password is used. Upload access is still verified against the Supabase administrator role.</p>
        </section>
      </div>
      <footer className="border-t border-white/10 py-4 text-xs tracking-wide text-white/40">ROYAL SCOUT · PUBLIC ANALYTICS, ADMIN-ONLY INGESTION</footer>
    </div>
  </main>;
}

export default function LoginPage() {
  return <Suspense fallback={<main className="private-entry grid min-h-screen place-items-center text-white">Opening secure sign-in…</main>}><LoginForm /></Suspense>;
}
