"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Database } from "lucide-react";
import type { DatasetOption } from "@/lib/dataset-types";
import { primaryDatasetId } from "@/lib/dataset-selection";

export function DatasetSelector({ datasets, selectedId }: { datasets: DatasetOption[]; selectedId: string | null }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!datasets.length) return null;

  async function select(value: string) {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/datasets/active", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dataset_id: value || null }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(payload?.error ?? "Could not switch dataset.");
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not switch dataset.");
    } finally {
      setBusy(false);
    }
  }

  const primaryId = primaryDatasetId(datasets) ?? "";
  const value = selectedId === primaryId ? "" : selectedId ?? "";
  return (
    <label className="flex min-w-0 items-center gap-2 text-xs text-ink-soft" title={error ?? "Select a successfully processed dataset"}>
      <Database className="hidden h-3.5 w-3.5 shrink-0 sm:block" aria-hidden="true" />
      <span className="sr-only">Active dataset</span>
      <select
        aria-label="Active dataset"
        className="input max-w-[42vw] sm:max-w-64"
        value={value}
        disabled={busy || datasets.length < 2}
        onChange={(event) => void select(event.target.value)}
      >
        <option value="">Primary source · {datasets.find((dataset) => dataset.dataset_id === primaryId)?.name}</option>
        {datasets.filter((dataset) => dataset.dataset_id !== primaryId).map((dataset) => (
          <option key={dataset.dataset_id} value={dataset.dataset_id}>
            {dataset.name}{dataset.is_fixture ? " · TEST DATA" : ""} · {new Date(dataset.created_at).toLocaleDateString()}
          </option>
        ))}
      </select>
      {busy ? <span className="text-2xs text-ink-faint" aria-live="polite">Loading…</span> : null}
      {error ? <span role="alert" className="sr-only">{error}</span> : null}
    </label>
  );
}
