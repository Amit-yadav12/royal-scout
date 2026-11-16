/** Client-side CSV export so downloads always match the on-screen filters. */
export function downloadCsv(filename: string, rows: Record<string, unknown>[], columns: { key: string; label: string }[], provenance: Record<string, unknown> = {}) {
  const lines: string[] = [];
  lines.push(`# Royal Scout Intelligence Hub export`);
  for (const [k, v] of Object.entries(provenance)) {
    lines.push(`# ${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`);
  }
  lines.push("#");
  lines.push(columns.map((c) => escape(c.label)).join(","));
  for (const row of rows) {
    lines.push(columns.map((c) => escape(format(row[c.key]))).join(","));
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function format(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (Array.isArray(v)) return v.join("; ");
  return String(v);
}

function escape(v: string): string {
  if (/[",\n]/.test(v)) return `"${v.replace(/"/g, '""')}"`;
  return v;
}
