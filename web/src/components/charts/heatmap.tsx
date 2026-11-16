import { cn } from "@/lib/cn";

export function Heatmap({
  rows,
  columns,
  values,
  format = (v: number | null) => (v === null ? "—" : v.toFixed(0)),
  legend,
}: {
  rows: string[];
  columns: string[];
  values: Record<string, Record<string, number | null>>;
  format?: (v: number | null) => string;
  legend?: string;
}) {
  const flat = rows.flatMap((r) => columns.map((c) => values[r]?.[c] ?? null)).filter((v): v is number => v !== null);
  const min = flat.length ? Math.min(...flat) : 0;
  const max = flat.length ? Math.max(...flat) : 100;
  const colour = (v: number | null) => {
    if (v === null) return "bg-surface-muted text-ink-faint";
    const t = max === min ? 0.5 : (v - min) / (max - min);
    // restrained navy→pink ramp, no neon
    if (t > 0.82) return "bg-royal-pink/85 text-white";
    if (t > 0.62) return "bg-royal-pink/55 text-white";
    if (t > 0.42) return "bg-navy-700/35 text-ink";
    if (t > 0.22) return "bg-navy-700/20 text-ink";
    return "bg-navy-700/8 text-ink-soft";
  };
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-2xs">
        <thead>
          <tr>
            <th className="px-2 py-1.5 text-left font-semibold text-ink-faint">Player</th>
            {columns.map((c) => (
              <th key={c} className="px-2 py-1.5 text-center font-semibold whitespace-nowrap text-ink-faint">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r} className="border-t border-surface-line/70">
              <td className="max-w-[190px] truncate px-2 py-1 text-ink">{r}</td>
              {columns.map((c) => (
                <td key={c} className="p-0.5">
                  <div className={cn("rounded px-1.5 py-1 text-center font-mono tabular-nums", colour(values[r]?.[c] ?? null))}>
                    {format(values[r]?.[c] ?? null)}
                  </div>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {legend ? <p className="mt-2 text-2xs text-ink-faint">{legend}</p> : null}
    </div>
  );
}
