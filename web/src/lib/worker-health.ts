export const WORKER_HEALTH_TIMEOUT_MS = 26_000;
export const WORKER_AUTO_RETRIES = 5;

/** Exponential wake-up backoff, capped so retries never become an infinite request loop. */
export function workerRetryDelay(attempt: number): number {
  const safeAttempt = Math.max(1, Math.floor(attempt));
  return Math.min(20_000, 1_500 * 2 ** (safeAttempt - 1));
}

export function workerHealthState(payload: unknown): "ok" | "unavailable" | "not_configured" {
  if (!payload || typeof payload !== "object") return "unavailable";
  const report = payload as { worker?: unknown; ready?: unknown; uploads_enabled?: unknown; configured?: Record<string, unknown> };
  if (report.worker === "ok" && report.ready === true && report.uploads_enabled === true) return "ok";
  if (report.worker === "not_configured" || report.configured?.worker_api_url === false) return "not_configured";
  return "unavailable";
}
