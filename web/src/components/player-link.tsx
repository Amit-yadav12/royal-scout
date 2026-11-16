import Link from "next/link";
import { cn } from "@/lib/cn";
import type { PlayerRow } from "@/lib/types";

export function PlayerLink({ name, className, meta }: { name: string; className?: string; meta?: string | null }) {
  return (
    <Link href={`/players/${encodeURIComponent(name)}`} className={cn("group block min-w-0", className)}>
      <span className="block truncate font-medium text-ink group-hover:text-royal-pink">{name}</span>
      {meta ? <span className="block truncate text-2xs text-ink-faint">{meta}</span> : null}
    </Link>
  );
}

export function teamLabel(row: PlayerRow): string {
  return (row.teams ?? []).slice(0, 2).join(", ") || "—";
}
