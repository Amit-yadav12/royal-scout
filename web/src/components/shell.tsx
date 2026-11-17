import Link from "next/link";
import { Suspense } from "react";
import { BarChart3, Download, FileSearch } from "lucide-react";
import { hasBundle, scopeOptions, datasetBadge } from "@/lib/bundle";
import { loadDashboardDataset } from "@/lib/server-dataset";
import { DatasetSelector } from "./dataset-selector";
import { ScopeSelect } from "./scope-select";
import { Badge } from "./ui/badge";
import { SignOutButton } from "./sign-out-button";
import { BrandLockup } from "./brand-mark";
import { ThemeToggle } from "./theme-provider";
import { ActiveNavLink, type NavIconName } from "./active-nav-link";
import { createServerSupabase } from "@/lib/supabase";
import { isPlatformAdmin } from "@/lib/staff-access";

const NAV_GROUPS: { label: string; items: { href: string; label: string; icon: NavIconName }[] }[] = [
  {
    label: "Command",
    items: [
      { href: "/", label: "Overview", icon: "LayoutDashboard" },
      { href: "/data-center", label: "Data Center", icon: "Database" },
      { href: "/data-audit", label: "Data Audit", icon: "ShieldAlert" },
    ],
  },
  {
    label: "Analytics",
    items: [
      { href: "/batting", label: "Batting Analytics", icon: "TrendingUp" },
      { href: "/bowling", label: "Bowling Analytics", icon: "Target" },
      { href: "/pressure", label: "Pressure Analytics", icon: "Gauge" },
      { href: "/pressure-audit", label: "Pressure Ranking (audited)", icon: "ShieldCheck" },
      { href: "/statistical", label: "Statistical Intelligence", icon: "Brain" },
    ],
  },
  {
    label: "Rankings",
    items: [
      { href: "/top-batters", label: "Top 30 Batters", icon: "ListOrdered" },
      { href: "/top-bowlers", label: "Top 30 Bowlers", icon: "ListOrdered" },
      { href: "/stability", label: "Ranking Stability", icon: "Activity" },
    ],
  },
  {
    label: "Scouting",
    items: [
      { href: "/players", label: "Player Explorer", icon: "Users" },
      { href: "/compare", label: "Player Comparison", icon: "GitCompareArrows" },
      { href: "/exports", label: "Export Center", icon: "Download" },
      { href: "/methodology", label: "Methodology & Settings", icon: "Sliders" },
    ],
  },
];

const SECTION_HELP: Record<string, string> = {
  "/": "Dataset health, capability coverage and the headline findings.",
  "/data-center": "Every dataset version, original file, hash and derived artefact.",
  "/ingestion": "Administrator-only dataset upload and processing.",
  "/data-audit": "Column-level audit, cricket-rule validation and a transparent quality score.",
  "/batting": "Batting output, distribution and the components behind each score.",
  "/bowling": "Workload, wicket-taking and containment, with specialist classification.",
  "/pressure": "Situation-based pressure analysis — only where the data supports it.",
  "/statistical": "Shrinkage, confidence, coverage and metric availability.",
  "/top-batters": "Reliability-adjusted Top 30 batters, filterable and re-rankable.",
  "/top-bowlers": "Reliability-adjusted Top 30 bowlers, filterable and re-rankable.",
  "/stability": "How much the ranking moves when the methodology changes.",
  "/players": "Every player record in the dataset with sample-size context.",
  "/compare": "Up to four players, normalised and role-aware.",
  "/exports": "Download rankings, audits and the full analytical workbook.",
  "/methodology": "Exact definitions, weights and thresholds in force.",
};

export async function Shell({ children }: { children: React.ReactNode }) {
  const [datasetContext, session] = await Promise.all([loadDashboardDataset(), createServerSupabase()]);
  let isAdmin = false;
  let authenticated = false;
  if (session) {
    const { data: { user } } = await session.auth.getUser();
    if (user) {
      authenticated = true;
      isAdmin = await isPlatformAdmin(session, user.id);
    }
  }
  const navGroups = isAdmin
    ? [...NAV_GROUPS, { label: "Administrator", items: [
        { href: "/ingestion", label: "Data Ingestion", icon: "UploadCloud" as NavIconName },
      ] }]
    : NAV_GROUPS;
  const bundle = datasetContext.bundle;
  const ready = hasBundle(bundle);
  const isFixture = ready ? bundle.meta.is_fixture : false;
  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-navy-800 bg-navy-900 text-white lg:flex">
        <div className="border-b border-white/10 px-4 py-4">
          <BrandLockup />
        </div>
        <nav className="flex-1 overflow-y-auto px-2 py-3">
          {navGroups.map((group) => (
            <div key={group.label} className="mb-4">
              <p className="px-2 pb-1 text-[0.6rem] font-semibold tracking-[0.16em] text-white/35 uppercase">
                {group.label}
              </p>
              <ul className="space-y-0.5">
                {group.items.map((item) => (
                  <li key={item.href}>
                    <ActiveNavLink href={item.href} label={item.label} iconName={item.icon} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <div className="border-t border-white/10 px-4 py-3 text-2xs leading-relaxed text-white/40">
          <p className="font-mono">{ready ? `model ${bundle.meta.model_version}` : "no bundle"}</p>
          <p className="mt-0.5 truncate">{ready ? bundle.meta.config_fingerprint : "—"}</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col lg:pl-60">
        <header className="sticky top-0 z-20 border-b border-surface-line bg-surface/95 backdrop-blur">
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 sm:px-6">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="truncate text-sm font-semibold text-ink">Royal Scout Intelligence OS</h1>
                {datasetContext.embeddedSnapshot ? (
                  <Badge tone="warning">LOCAL BUILD SNAPSHOT</Badge>
                ) : isFixture ? (
                  <Badge tone="warning">SYNTHETIC TEST DATA</Badge>
                ) : ready ? (
                  <Badge tone="positive">live dataset</Badge>
                ) : (
                  <Badge tone="neutral">no active dataset</Badge>
                )}
              </div>
              <p className="mt-0.5 truncate text-2xs text-ink-faint">
                Every Player. Every Metric. Every Insight. · {datasetBadge(bundle)}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <DatasetSelector datasets={datasetContext.datasets} selectedId={datasetContext.selectedId} />
              <Suspense fallback={<div className="h-7 w-48 rounded border border-surface-line bg-surface-muted" />}>
                <ScopeSelect options={scopeOptions(bundle)} />
              </Suspense>
              <Link href="/exports" className="btn hidden sm:inline-flex">
                <Download className="h-3.5 w-3.5" /> Exports
              </Link>
              <ThemeToggle />
              <SignOutButton authenticated={authenticated} />
            </div>
          </div>
          <nav aria-label="Dashboard navigation" className="flex gap-1 overflow-x-auto border-t border-surface-line px-3 py-2 lg:hidden">
            {navGroups.flatMap((group) => group.items).map((item) => (
              <ActiveNavLink key={item.href} href={item.href} label={item.label} mobile />
            ))}
          </nav>
          {datasetContext.embeddedSnapshot ? (
            <div className="border-t border-amber-200 bg-amber-50 px-4 py-1.5 text-2xs text-amber-900 sm:px-6" role="status">
Local development is showing the build-time snapshot; production loads the selected private dataset at request time.
              {datasetContext.error ? ` Live dataset unavailable: ${datasetContext.error}` : ""}
            </div>
          ) : datasetContext.error ? (
            <div className="border-t border-amber-200 bg-amber-50 px-4 py-1.5 text-2xs text-amber-900 sm:px-6" role="status">
              {datasetContext.error} No unrelated snapshot has been substituted.
            </div>
          ) : null}
          {isFixture ? (
            <div className="border-t border-amber-200 bg-amber-50 px-4 py-1.5 text-2xs text-amber-900 sm:px-6">
              <strong className="font-semibold">This deployment is running on a synthetic fixture dataset.</strong>{" "}
              Names and numbers are generated for demonstration and testing. Import real scouting data before making
              any selection decision — production rankings stay empty until a genuine dataset is ingested.
            </div>
          ) : null}
        </header>
        <main className="min-w-0 flex-1 px-4 py-5 motion-enter sm:px-6 lg:px-8">{children}</main>
        <footer className="border-t border-surface-line px-4 py-3 text-2xs text-ink-faint sm:px-6 lg:px-8">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span>
              {ready ? (
                <>
                  Analysed {bundle.meta.created_at.replace("T", " ").replace("+00:00", " UTC")} ·{" "}
                  {bundle.meta.processing_seconds}s processing · quality score {bundle.quality.score.toFixed(1)}/100
                </>
              ) : (
                "No analytical bundle loaded"
              )}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <FileSearch className="h-3 w-3" /> All figures are computed by the Python engine and carried with their
              coverage and confidence.
            </span>
          </div>
        </footer>
      </div>
    </div>
  );
}

export function PageHeader({
  title,
  description,
  icon: Icon = BarChart3,
  actions,
}: {
  title: string;
  description?: string;
  icon?: any;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div className="flex items-start gap-2.5">
        <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-lg bg-navy-900 text-white shadow-sm ring-1 ring-white/10">
          <Icon className="h-4 w-4" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          {description ? <p className="mt-0.5 max-w-3xl text-xs leading-relaxed text-ink-soft">{description}</p> : null}
        </div>
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
