export const MAX_UPLOAD_FILES = 200;
export const MAX_SINGLE_UPLOAD_BYTES = 2 * 1024 ** 3;
export const MAX_UPLOAD_BATCH_BYTES = 10 * 1024 ** 3;

const SUPPORTED_EXTENSIONS = [
  ".tar.gz", ".zip", ".tar", ".tgz", ".csv", ".tsv", ".xlsx", ".xls", ".jsonl", ".json",
  ".parquet", ".feather", ".ods", ".xml", ".pdf", ".docx",
];

export function validateUploadFiles(files: readonly { name: string; size: number }[]): string | null {
  if (!files.length) return "Choose at least one cricket data file.";
  if (files.length > MAX_UPLOAD_FILES) return `Choose no more than ${MAX_UPLOAD_FILES} files per upload.`;
  let total = 0;
  for (const file of files) {
    const name = file.name.trim().toLowerCase();
    if (!SUPPORTED_EXTENSIONS.some((extension) => name.endsWith(extension))) {
      return `${file.name}: unsupported file type. Supported formats are ZIP/TAR, CSV/TSV, Excel/ODS, JSON/JSONL, Parquet/Feather, XML, PDF and DOCX.`;
    }
    if (!Number.isSafeInteger(file.size) || file.size <= 0) return `${file.name}: file is empty or has an invalid size.`;
    if (file.size > MAX_SINGLE_UPLOAD_BYTES) return `${file.name}: exceeds the 2 GiB per-file limit.`;
    total += file.size;
    if (total > MAX_UPLOAD_BATCH_BYTES) return "This batch exceeds the 10 GiB total upload limit.";
  }
  return null;
}

export const ACCEPTED_UPLOAD_TYPES = SUPPORTED_EXTENSIONS.join(",");
