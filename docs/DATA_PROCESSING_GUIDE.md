# Data processing guide

This is what the engine does with your files, and what it refuses to do.

## 1. Accepted inputs

| Family | Extensions | Notes |
| --- | --- | --- |
| Delimited | `.csv` `.tsv` `.txt` | delimiter sniffed, preamble rows skipped, multiple tables in one file detected |
| JSON | `.json` `.jsonl` `.ndjson` | objects, arrays of objects, JSONL streams; nested keys flattened with a path |
| Excel | `.xlsx` `.xls` `.xlsm?` `.ods` | every worksheet profiled separately; macro-enabled files are refused, not patched |
| XML | `.xml` | repeated child elements become rows |
| Columnar | `.parquet` `.feather` | read with PyArrow; schema retained |
| Documents | `.pdf` `.docx` | table extraction (PDF via `pdfplumber`, DOCX via `python-docx`); OCR optional and flagged |
| Archives | `.zip` `.tar` `.tar.gz` `.tgz` `.7z` | extracted safely, recursively, with nested-folder support |

Unsupported but *known*: `.xlsb` (no reader), `.7z`/PDF when the optional library is absent.
Both produce a named `IngestionError` with the file path — never a silent skip.

## 2. Safety rules during extraction

* path traversal (`../`, absolute paths, symlinks escaping the root) → entry rejected, logged;
* zip bombs: entry count > `RS_MAX_ARCHIVE_ENTRIES`, expansion ratio > `RS_MAX_COMPRESSION_RATIO`
  or total > `RS_MAX_EXTRACTED_BYTES` → archive rejected with the measured numbers;
* encrypted archives/entries → rejected (we do not attempt password cracking);
* executables, scripts and macro-enabled Office files → rejected by content sniffing, not just
  by extension, and never executed;
* nesting depth capped (`RS_MAX_NESTED_DEPTH`), each level logged with its own path.

Every entry appears in the archive inspection table with `size_bytes`, `compressed_bytes`,
depth and the reason it was or was not extracted. After a job, the Data Ingestion page shows
the file log: `File | Origin | Kind | Tables | Rows | Record type | Status | Reason`.

## 3. Schema discovery and mapping

For each table the engine scores candidate columns against the canonical fields
(`player`, `runs`, `balls_faced`, `overs`, `wickets`, `match_id`, `season`, …) using header
similarity plus value-shape evidence (numeric density, overs notation, wicket labels). A
mapping is auto-applied above the confidence threshold; below it the table is listed as
*unmapped* with its best candidates and the mapping UI is used to confirm. Nothing is dropped
because a header was unfamiliar — it is reported.

## 4. Granularity, and why it matters

| Granularity | What the engine can compute | What it cannot |
| --- | --- | --- |
| ball-by-ball | everything, including phase and pressure | — |
| innings-level | batting/bowling rates, consistency (innings dispersion), splits | phase, pressure |
| aggregate/season-level | shrunk rates, coverage-limited composites | consistency (label switches to `aggregate_dispersion`), pressure |

The active granularity is printed per player (`Batting granularity: innings`) and on the Data
Center page as a capability matrix. A metric whose requirement is unmet appears as
**unavailable with a reason**, and the composite coverage drops accordingly.

## 5. Metric classification (A/B/C/D)

* **A — available:** present in the source and validated.
* **B — derivable:** computed exactly from other fields (strike rate, economy, average).
* **C — needs external verification:** cannot be confirmed from the dataset alone (birth date,
  overseas status, injury history).
* **D — unavailable:** the dataset cannot support it at all (e.g. pressure without deliveries).

`metric_availability` is stored per dataset version and rendered on Statistical Intelligence.

## 6. Data Quality Score

A weighted roll-up of completeness, validity, consistency and duplication, minus penalties for
high-severity findings. The fixture dataset scores **95.01/100** with 4 findings — the score is
published beside the findings, never instead of them.

## 7. Identity resolution

Names are normalised (case, punctuation, initials, diacritics) and matched against the existing
roster. Exact and high-confidence fuzzy matches are applied automatically and recorded as
aliases; ambiguous cases go to `player_identity_reviews` for a human decision. The Data Audit
page shows the review queue and the alias evidence. Two players are never merged on a
first-name collision alone.

## 8. Adding data to an existing dataset

1. Data Ingestion → choose files (or a ZIP of a new season).
2. Set the dataset name, submit; the worker stages, extracts and analyses.
3. The pipeline writes a **new dataset version**; the old one stays queryable for comparison.
4. The dashboard header lets you switch scope (competition, season, team) and the Export Center
   records the active scope in every file.

Duplicate files (identical SHA-256) are recognised and skipped with an explicit
`duplicate` status so records are never double-counted.

## 9. What "reprocess" and "version compare" mean here

* **Reprocess:** run the pipeline again over the same sources — used after a mapping fix or a
  configuration change. Output is a new version with a new `config_fingerprint`.
* **Version compare:** the Data Center lists versions with record counts and quality scores;
  the API exposes the bundle per dataset/version so two versions can be diffed without
  touching the production snapshot.

## 10. Data hygiene checklist before importing real data

- [ ] One row = one entity (innings, spell or delivery). Mixed granularity in one worksheet is
      detected but should be split.
- [ ] Dismissals are distinguishable from not-outs. Without this, average is unavailable — not
      approximated from innings.
- [ ] Overs use cricket notation (`3.4`), not decimals.
- [ ] Team/opposition columns describe the player's side, not the innings.
- [ ] Duplicate scorecard rows are removed at source where possible; the engine flags them but
      cannot know which copy is canonical.
- [ ] Fixture/placeholder names are removed before a production run.

## Provider-specific packs

A data pack that matches `royalscout/providers/*.py` is canonicalised by the adapter before the
generic alias inference runs. The SupeRR Selector pack is the reference example: `runs` holds bat
runs only, extras live in `extras1_runs` / `extras_2_runs`, `extras_type` uses the literal string
`"None"`, there is no running score, and `over_ball_num` counts illegal deliveries. Those quirks are
handled in `royalscout/superr/load.py` and documented in `reports/Audit_Report.md`.
