"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { axisProps, CHART, tooltipStyle } from "./theme";

export function RankedBars({
  data,
  valueLabel,
  height = 340,
  colour = CHART.blue,
}: {
  data: { name: string; value: number | null; highlight?: boolean }[];
  valueLabel: string;
  height?: number;
  colour?: string;
}) {
  const rows = data.filter((d) => d.value !== null).slice(0, 15);
  if (!rows.length) return <p className="py-10 text-center text-xs text-ink-faint">No values available.</p>;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 18, bottom: 4, left: 8 }}>
        <CartesianGrid stroke={CHART.grid} strokeDasharray="2 3" horizontal={false} />
        <XAxis type="number" {...axisProps} />
        <YAxis
          type="category"
          dataKey="name"
          width={110}
          {...axisProps}
          tick={{ fill: CHART.axis, fontSize: 9 }}
          tickFormatter={(v: string) => shortName(v)}
        />
        <Tooltip
          {...tooltipStyle}
          formatter={(v: number) => [Number(v).toFixed(1), valueLabel]}
          labelFormatter={(label: string) => label}
        />
        <Bar dataKey="value" radius={[0, 3, 3, 0]} barSize={13}>
          {rows.map((r) => (
            <Cell key={r.name} fill={r.highlight ? CHART.pink : colour} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function MiniBar({
  value,
  max = 100,
  colour = CHART.blue,
  label,
  showValue = true,
}: {
  value: number | null;
  max?: number;
  colour?: string;
  label?: string;
  showValue?: boolean;
}) {
  const pct = value === null ? 0 : Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="flex items-center gap-2" title={label}>
      <div className="h-1.5 w-full min-w-[48px] overflow-hidden rounded-full bg-surface-deep">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: colour }} />
      </div>
      {showValue ? (
        <span className="w-9 shrink-0 text-right font-mono text-2xs tabular-nums text-ink-soft">
          {value === null ? "—" : value.toFixed(0)}
        </span>
      ) : null}
    </div>
  );
}

/** Axis labels keep the last two words so long names never wrap into each other. */
function shortName(name: string): string {
  const parts = String(name).split(/\s+/);
  return parts.length > 2 ? parts.slice(-2).join(" ") : String(name);
}
