const REQUIRED_SUPERR_TABLES = [
  { name: "ball-by-ball", columns: ["match_id", "innings", "overid", "striker_id", "bowler_id"] },
  { name: "matches", columns: ["match_id", "comp_id", "match_date", "result"] },
  { name: "competitions", columns: ["comp_id", "comp_name", "match_format"] },
  { name: "playing eleven", columns: ["match_id", "player_id", "is_played"] },
  { name: "competition/player mapping", columns: ["player_id", "player_name", "team_id", "comp_id"] },
] as const;

function splitCsvHeader(line: string, delimiter: string): string[] {
  const fields: string[] = [];
  let value = "";
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (char === '"') {
      if (quoted && line[i + 1] === '"') {
        value += '"';
        i += 1;
      } else {
        quoted = !quoted;
      }
    } else if (char === delimiter && !quoted) {
      fields.push(value);
      value = "";
    } else {
      value += char;
    }
  }
  fields.push(value);
  return fields.map((field) => field.replace(/^\uFEFF/, "").trim().toLowerCase());
}

function parseHeader(header: string): Set<string> {
  const firstLine = header.split(/\r?\n/, 1)[0] ?? "";
  const delimiter = [",", "\t", ";", "|"]
    .map((candidate) => ({ candidate, count: firstLine.split(candidate).length - 1 }))
    .sort((a, b) => b.count - a.count)[0]?.candidate ?? ",";
  return new Set(splitCsvHeader(firstLine, delimiter));
}

/**
 * A SupeRR ball-by-ball CSV requires its four companion tables in the same
 * upload batch. Previous datasets are intentionally isolated, so do not imply
 * that files from another upload can complete this pack.
 */
export function validateSuperrPackHeaders(
  files: readonly { name: string; header: string }[],
  containsArchive = false,
): string | null {
  // Archives may contain companion tables we cannot inspect in the browser.
  if (containsArchive) return null;
  const headers = files.map(({ header }) => parseHeader(header));
  const hasBallByBall = headers.some((columns) =>
    REQUIRED_SUPERR_TABLES[0].columns.every((column) => columns.has(column)));
  if (!hasBallByBall) return null;

  const missing = REQUIRED_SUPERR_TABLES.slice(1)
    .filter(({ columns }) => !headers.some((header) => columns.every((column) => header.has(column))))
    .map(({ name }) => name);
  if (!missing.length) return null;
  return `This looks like a SupeRR ball-by-ball upload, but this batch is missing required tables: ${missing.join(", ")}. Include all five core CSV tables in the same upload (ball-by-ball, matches, competitions, playing eleven, and competition/player mapping). Teams are optional. Files from earlier uploads are not combined into this dataset.`;
}

export function isIncompleteSuperrPackError(error: string | null | undefined): boolean {
  return Boolean(error?.includes("SupeRR pack is missing required table(s):"));
}
