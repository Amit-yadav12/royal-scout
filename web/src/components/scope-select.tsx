"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTransition } from "react";
import { Layers } from "lucide-react";
type ScopeOption = { label: string; type: string; count: number };

export function ScopeSelect({ options }: { options: ScopeOption[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [pending, startTransition] = useTransition();
  const current = params.get("scope") ?? "global";

  if (!options.length) return null;

  return (
    <label className="flex items-center gap-1.5 rounded border border-surface-line bg-surface px-2 py-1">
      <Layers className="h-3.5 w-3.5 text-ink-faint" />
      <span className="hidden text-2xs tracking-wide text-ink-faint uppercase sm:inline">Scope</span>
      <select
        aria-label="Dataset filter scope"
        className="max-w-[190px] bg-transparent text-xs text-ink focus:outline-none"
        value={current}
        disabled={pending}
        onChange={(e) => {
          const next = new URLSearchParams(Array.from(params.entries()));
          const value = e.target.value;
          if (value === "global" || !value) next.delete("scope");
          else next.set("scope", value);
          startTransition(() => router.push(`${pathname}?${next.toString()}`, { scroll: false }));
        }}
      >
        <option value="global">All data (global)</option>
        {options
          .filter((o) => o.type !== "global")
          .map((o) => (
            <option key={o.label} value={o.label}>
              {o.type === "competition" ? "Competition · " : o.type === "season" ? "Season · " : o.type === "team" ? "Team · " : ""}
              {o.label}
            </option>
          ))}
      </select>
    </label>
  );
}
