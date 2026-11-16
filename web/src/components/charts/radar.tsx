"use client";

import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Tooltip, Legend } from "recharts";
import { CHART, tooltipStyle } from "./theme";

const PALETTE = [CHART.pink, CHART.blue, CHART.gold, CHART.teal];

export function PlayerRadar({
  metrics,
  series,
  height = 320,
}: {
  metrics: string[];
  series: { name: string; values: (number | null)[] }[];
  height?: number;
}) {
  const data = metrics.map((m, i) => {
    const row: Record<string, string | number | null> = { metric: m };
    series.forEach((s) => {
      row[s.name] = s.values[i];
    });
    return row;
  });
  const usable = series.filter((s) => s.values.some((v) => v !== null));
  if (!usable.length) {
    return <p className="py-10 text-center text-xs text-ink-faint">None of these components are available for the selected players.</p>;
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RadarChart data={data} outerRadius="72%">
        <PolarGrid stroke={CHART.grid} />
        <PolarAngleAxis dataKey="metric" tick={{ fill: CHART.axis, fontSize: 10 }} />
        <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fill: CHART.axis, fontSize: 9 }} stroke={CHART.grid} />
        {usable.map((s, i) => (
          <Radar key={s.name} name={s.name} dataKey={s.name} stroke={PALETTE[i % PALETTE.length]}
            fill={PALETTE[i % PALETTE.length]} fillOpacity={0.14} strokeWidth={1.6} />
        ))}
        <Tooltip {...tooltipStyle} formatter={(v: number) => (v === null ? "—" : Number(v).toFixed(1))} />
        <Legend wrapperStyle={{ fontSize: 10 }} />
      </RadarChart>
    </ResponsiveContainer>
  );
}
