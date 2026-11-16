"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { axisProps, CHART, tooltipStyle } from "./theme";

const PALETTE = [CHART.pink, CHART.blue, CHART.gold, CHART.teal];

export function TrendChart({
  data,
  xKey,
  series,
  height = 280,
  yLabel,
}: {
  data: Record<string, string | number | null>[];
  xKey: string;
  series: { key: string; label: string }[];
  height?: number;
  yLabel?: string;
}) {
  if (!data.length) return <p className="py-10 text-center text-xs text-ink-faint">No trend data available.</p>;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 14, bottom: 4, left: -12 }}>
        <CartesianGrid stroke={CHART.grid} strokeDasharray="2 3" />
        <XAxis dataKey={xKey} {...axisProps} />
        <YAxis {...axisProps} label={yLabel ? { value: yLabel, angle: -90, position: "insideLeft", fontSize: 10, fill: CHART.axis } : undefined} />
        <Tooltip {...tooltipStyle} formatter={(v: number) => (v === null ? "—" : Number(v).toFixed(2))} />
        <Legend wrapperStyle={{ fontSize: 10 }} />
        {series.map((s, i) => (
          <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={PALETTE[i % PALETTE.length]}
            strokeWidth={1.8} dot={{ r: 2.5 }} connectNulls />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
