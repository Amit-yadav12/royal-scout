import { cn } from "@/lib/cn";
import { gradeTone } from "@/lib/format";

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: React.ReactNode;
  tone?: "neutral" | "navy" | "pink" | "gold" | "positive" | "warning" | "danger" | "info";
  className?: string;
}) {
  const tones: Record<string, string> = {
    neutral: "bg-slate-100 text-slate-700 ring-slate-200",
    navy: "bg-navy-900 text-white ring-navy-800",
    pink: "bg-royal-pink/10 text-royal-pinkDark ring-royal-pink/25",
    gold: "bg-royal-gold/10 text-[#7a6013] ring-royal-gold/30",
    positive: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    warning: "bg-amber-50 text-amber-800 ring-amber-200",
    danger: "bg-rose-50 text-rose-700 ring-rose-200",
    info: "bg-sky-50 text-sky-700 ring-sky-200",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-2xs font-medium ring-1 ring-inset",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function GradeBadge({ grade }: { grade?: string | null }) {
  if (!grade) return <span className="text-ink-faint">—</span>;
  return (
    <span
      title={`Confidence grade ${grade}`}
      className={cn("inline-flex h-5 w-5 items-center justify-center rounded text-2xs font-bold ring-1 ring-inset", gradeTone(grade))}
    >
      {grade}
    </span>
  );
}
