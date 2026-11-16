"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { axisProps, CHART, tooltipStyle } from "./theme";

export function Histogram({
  values,
  label,
  bins = 10,
  colour = CHART.navy,
  height = 200,
}: {
  values: (number | null | undefined)[];
  label: string;
  bins?: number;
  colour?: string;
  height?: number;
}) {
  const nums = values.filter((v): v is number => typeof v === "number" && !Number.isNaN(v));
  if (!nums.length) return <p className="py-8 text-center text-xs text-ink-faint">No values available.</p>;
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const width = (max - min) / bins || 1;
  const buckets = Array.from({ length: bins }, (_, i) => ({
    bucket: `${(min + i * width).toFixed(width < 2 ? 1 : 0)}–${(min + (i + 1) * width).toFixed(width < 2 ? 1 : 0)}`,
    count: 0,
  }));
  for (const n of nums) {
    const idx = Math.min(bins - 1, Math.floor((n - min) / width));
    buckets[idx].count += 1;
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={buckets} margin={{ top: 6, right: 8, bottom: 4, left: -18 }}>
        <CartesianGrid stroke={CHART.grid} strokeDasharray="2 3" vertical={false} />
        <XAxis dataKey="bucket" {...axisProps} interval={0} tick={{ fill: CHART.axis, fontSize: 9 }} />
        <YAxis {...axisProps} allowDecimals={false} />
        <Tooltip {...tooltipStyle} formatter={(v: number) => [`${v} player(s)`, label]} />
        <Bar dataKey="count" fill={colour} radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
