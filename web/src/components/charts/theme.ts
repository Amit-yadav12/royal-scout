export const CHART = {
  navy: "#102A54",
  blue: "#1B4B8F",
  pink: "#E8117F",
  gold: "#C9A227",
  teal: "#0F766E",
  slate: "#7A8699",
  grid: "#E4E8EF",
  axis: "#7A8699",
};

export const axisProps = {
  stroke: CHART.axis,
  tick: { fill: CHART.axis, fontSize: 10 },
  tickLine: false,
  axisLine: { stroke: CHART.grid },
} as const;

export const tooltipStyle = {
  contentStyle: {
    borderRadius: 6,
    border: `1px solid ${CHART.grid}`,
    boxShadow: "0 8px 24px rgba(11,27,51,0.10)",
    fontSize: 11,
    padding: "8px 10px",
    color: "#0B1B33",
  },
  labelStyle: { fontSize: 11, fontWeight: 600, color: "#0B1B33", marginBottom: 2 },
} as const;
