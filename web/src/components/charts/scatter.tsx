"use client";

import {
  CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import { axisProps, CHART, tooltipStyle } from "./theme";

export interface ScatterPoint {
  name: string;
  x: number | null;
  y: number | null;
  size?: number | null;
  group?: string | null;
}

export function MetricScatter({
  points,
  xLabel,
  yLabel,
  xMean,
  yMean,
  height = 320,
  highlight = [],
  onSelect,
}: {
  points: ScatterPoint[];
  xLabel: string;
  yLabel: string;
  xMean?: number;
  yMean?: number;
  height?: number;
  highlight?: string[];
  onSelect?: (name: string) => void;
}) {
  const data = points
    .filter((p) => p.x !== null && p.y !== null)
    .map((p) => ({ ...p, sizeValue: Math.max(24, Math.min(260, (p.size ?? 100) / 3)) }));
  if (!data.length) {
    return <p className="px-1 py-10 text-center text-xs text-ink-faint">No plottable values in this selection.</p>;
  }
  // Highlighted players are drawn as a second series so the default recharts
  // marker shape (and its radius from the ZAxis) is preserved.
  const highlighted = data.filter((p) => highlight.includes(p.name));
  const rest = data.filter((p) => !highlight.includes(p.name));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ScatterChart margin={{ top: 8, right: 12, bottom: 22, left: 4 }}>
        <CartesianGrid stroke={CHART.grid} strokeDasharray="2 3" />
        <XAxis type="number" dataKey="x" name={xLabel} {...axisProps}
          label={{ value: xLabel, position: "insideBottom", offset: -12, fontSize: 10, fill: CHART.axis }} />
        <YAxis type="number" dataKey="y" name={yLabel} {...axisProps}
          label={{ value: yLabel, angle: -90, position: "insideLeft", fontSize: 10, fill: CHART.axis }} />
        <ZAxis type="number" dataKey="sizeValue" range={[30, 260]} />
        <Tooltip
          {...tooltipStyle}
          cursor={{ strokeDasharray: "3 3" }}
          formatter={(value: number, key: string) => [typeof value === "number" ? value.toFixed(2) : value, key]}
          labelFormatter={() => ""}
          content={({ payload }) => {
            if (!payload || !payload.length) return null;
            const p = payload[0].payload as ScatterPoint;
            return (
              <div style={tooltipStyle.contentStyle}>
                <p style={tooltipStyle.labelStyle}>{p.name}</p>
                <p>{xLabel}: {p.x?.toFixed(2)}</p>
                <p>{yLabel}: {p.y?.toFixed(2)}</p>
                {p.size ? <p>Exposure: {Math.round(p.size)} balls</p> : null}
              </div>
            );
          }}
        />
        {xMean !== undefined ? <ReferenceLine x={xMean} stroke={CHART.gold} strokeDasharray="3 4" /> : null}
        {yMean !== undefined ? <ReferenceLine y={yMean} stroke={CHART.gold} strokeDasharray="3 4" /> : null}
        <Scatter
          data={rest}
          fill={CHART.blue}
          fillOpacity={0.72}
          name={yLabel}
          onClick={(p: any) => p?.name && onSelect?.(p.name)}
        />
        {highlighted.length ? (
          <Scatter
            data={highlighted}
            fill={CHART.pink}
            fillOpacity={0.9}
            name="Highlighted"
            onClick={(p: any) => p?.name && onSelect?.(p.name)}
          />
        ) : null}
      </ScatterChart>
    </ResponsiveContainer>
  );
}
