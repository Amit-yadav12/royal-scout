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
    if (!unique.has(record.dataset_id)) unique.set(record.dataset_id, {
      dataset_id: record.dataset_id,
      name: record.dataset_name,
      created_at: record.finished_at || record.created_at,
      is_fixture: Boolean(record.is_fixture),
    });
  }
  return [...unique.values()];
}

export function resolveDatasetSelection(requestedId: string | null, datasets: DatasetOption[]) {
  if (!datasets.length) return { selectedId: null, error: "No successfully processed dataset is available yet." };
  if (requestedId && !datasets.some((dataset) => dataset.dataset_id === requestedId)) {
    return { selectedId: requestedId, error: "The selected dataset is no longer in processing history. Choose an available dataset." };
  }
  return { selectedId: requestedId ?? datasets[0].dataset_id, error: null };
}
