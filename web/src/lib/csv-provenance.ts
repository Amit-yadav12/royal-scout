/**
 * Shared CSV writer used by both the browser (client exports) and the API route
 * (server exports) so a downloaded file always carries the same provenance block.
 *
 * Rules enforced here:
 *  * a missing value is an empty cell — never the string "0" and never "null";
 *  * separators, quotes and newlines are quoted per RFC 4180;
 *  * provenance lines are `#`-commented and always precede the table.
 */
export function buildCsv(
  headers: string[],
  rows: (string | number | null | undefined)[][],
  provenance: Record<string, unknown> = {},
): string {
  const lines: string[] = [];
  const entries: [string, unknown][] = [["generated_utc_unused", null], ...Object.entries(provenance)];
  lines.push("# Royal Scout Intelligence Hub — analytical export");
  for (const [key, value] of entries) {
    if (key === "generated_utc_unused" && value === null) continue;
    const text = typeof value === "object" && value !== null ? JSON.stringify(value) : String(value);
    lines.push(`# ${key}: ${text}`);
  }
  if (!("calculated_at" in provenance) && !("generated_at_utc" in provenance)) {
    lines.push(`# calculated_at: ${new Date().toISOString()}`);
  }
  lines.push("#");
  lines.push(headers.map(escape).join(","));
  for (const row of rows) {
    lines.push(row.map((cell) => escape(cell === null || cell === undefined ? "" : String(cell))).join(","));
  }
  return lines.join("\n");
}

function escape(value: string): string {
  return /[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}
