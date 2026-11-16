"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity, Brain, Database, Download, Gauge, GitCompareArrows, LayoutDashboard, ListOrdered,
  ShieldAlert, ShieldCheck, Sliders, Target, TrendingUp, UploadCloud, Users,
} from "lucide-react";

const ICONS = {
  Activity, Brain, Database, Download, Gauge, GitCompareArrows, LayoutDashboard, ListOrdered,
  ShieldAlert, ShieldCheck, Sliders, Target, TrendingUp, UploadCloud, Users,
} as const;
export type NavIconName = keyof typeof ICONS;

export function ActiveNavLink({ href, label, iconName, mobile = false }: { href: string; label: string; iconName?: keyof typeof ICONS; mobile?: boolean }) {
  const pathname = usePathname();
  const active = href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
  const Icon = iconName ? ICONS[iconName] : null;
  if (mobile) {
    return <Link href={href} aria-current={active ? "page" : undefined} className={`shrink-0 rounded-md px-2.5 py-1.5 text-xs transition-colors ${active ? "bg-navy-900 font-medium text-white" : "text-ink-soft hover:bg-surface-muted hover:text-ink"}`}>{label}</Link>;
  }
  return (
    <Link href={href} aria-current={active ? "page" : undefined} className={`group flex items-center gap-2 rounded px-2 py-1.5 text-[0.79rem] transition-colors ${active ? "bg-white/10 font-medium text-white shadow-sm" : "text-white/70 hover:bg-white/8 hover:text-white"}`}>
      {Icon ? <Icon className={`h-3.5 w-3.5 shrink-0 ${active ? "text-royal-pink" : "text-white/40 group-hover:text-royal-pink"}`} aria-hidden="true" /> : null}
      <span className="truncate">{label}</span>
      {active ? <span className="ml-auto h-1.5 w-1.5 rounded-full bg-royal-pink" aria-hidden="true" /> : null}
    </Link>
  );
}
