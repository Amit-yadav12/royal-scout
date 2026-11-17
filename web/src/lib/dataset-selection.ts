import type { DatasetOption } from "@/lib/dataset-types";

export type SuccessfulDatasetRecord = {
  dataset_id: string;
  dataset_name: string;
  created_at: string;
  finished_at: string | null;
  is_fixture: boolean;
};

export function datasetOptionsFrom(records: SuccessfulDatasetRecord[]): DatasetOption[] {
  const unique = new Map<string, DatasetOption>();
  for (const record of records) {
    const current = unique.get(record.dataset_id);
    if (!current) {
      unique.set(record.dataset_id, {
        dataset_id: record.dataset_id,
        name: record.dataset_name,
        created_at: record.created_at,
        is_fixture: Boolean(record.is_fixture),
      });
      continue;
    }
    if (Date.parse(record.created_at) < Date.parse(current.created_at)) {
      unique.set(record.dataset_id, { ...current, created_at: record.created_at });
    }
  }
  return [...unique.values()];
}

/** Default to the most recently uploaded successful dataset; keep earlier datasets isolated and selectable. */
export function primaryDatasetId(datasets: DatasetOption[]): string | null {
  if (!datasets.length) return null;
  return [...datasets].sort((a, b) => {
    const aTime = Date.parse(a.created_at);
    const bTime = Date.parse(b.created_at);
    if (Number.isFinite(aTime) && Number.isFinite(bTime)) return bTime - aTime;
    return datasets.indexOf(a) - datasets.indexOf(b);
  })[0]?.dataset_id ?? null;
}

export function resolveDatasetSelection(requestedId: string | null, datasets: DatasetOption[]) {
  if (!datasets.length) return { selectedId: null, error: "No successfully processed dataset is available yet." };
  if (requestedId && !datasets.some((dataset) => dataset.dataset_id === requestedId)) {
    return { selectedId: requestedId, error: "The selected dataset is no longer in processing history. Choose an available dataset." };
  }
  return { selectedId: requestedId ?? primaryDatasetId(datasets), error: null };
}
