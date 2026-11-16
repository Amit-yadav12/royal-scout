import * as React from "react";
import { cn } from "@/lib/cn";

export function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <section className={cn("rounded-lg border border-surface-line bg-surface shadow-card", className)}>
      {children}
    </section>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
  className,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex items-start justify-between gap-4 border-b border-surface-line px-5 py-3.5", className)}>
      <div>
        <h2 className="text-[0.8125rem] font-semibold tracking-[0.06em] text-ink uppercase">{title}</h2>
        {subtitle ? <p className="mt-1 text-xs leading-relaxed text-ink-soft">{subtitle}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </header>
  );
}

export function CardBody({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("px-5 py-4", className)}>{children}</div>;
}

export function Stat({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  tone?: "default" | "pink" | "gold" | "positive" | "warning";
}) {
  const toneClass =
    tone === "pink"
      ? "text-royal-pink"
      : tone === "gold"
        ? "text-royal-gold"
        : tone === "positive"
          ? "text-emerald-700"
          : tone === "warning"
            ? "text-amber-700"
            : "text-ink";
  return (
    <div className="rounded-lg border border-surface-line bg-surface px-4 py-3.5 shadow-card">
      <p className="text-2xs font-medium tracking-[0.09em] text-ink-faint uppercase">{label}</p>
      <p className={cn("mt-1.5 font-mono text-2xl leading-none font-semibold tabular-nums", toneClass)}>{value}</p>
      {hint ? <p className="mt-1.5 text-2xs leading-relaxed text-ink-faint">{hint}</p> : null}
    </div>
  );
}

export function KeyValue({ label, value, mono = false }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-surface-line/70 py-1.5 last:border-0">
      <span className="text-xs text-ink-soft">{label}</span>
      <span className={cn("text-xs text-ink", mono && "font-mono tabular-nums")}>{value}</span>
    </div>
  );
}
