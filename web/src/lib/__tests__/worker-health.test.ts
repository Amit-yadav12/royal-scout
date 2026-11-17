import { describe, expect, it } from "vitest";
import { WORKER_AUTO_RETRIES, WORKER_HEALTH_TIMEOUT_MS, workerHealthState, workerRetryDelay } from "../worker-health";

describe("worker health retries", () => {
  it("caps timeouts and automatic health attempts", () => {
    expect(WORKER_HEALTH_TIMEOUT_MS).toBeLessThan(30_000);
    expect(WORKER_AUTO_RETRIES).toBe(5);
  });
  it("uses bounded exponential retry delays", () => {
    expect(workerRetryDelay(1)).toBe(1500);
    expect(workerRetryDelay(4)).toBe(12000);
    expect(workerRetryDelay(20)).toBe(20000);
  });
  it("enables upload only when every readiness gate explicitly passes", () => {
    expect(workerHealthState({ worker: "ok", ready: true, uploads_enabled: true })).toBe("ok");
    expect(workerHealthState({ worker: "ok", ready: true, uploads_enabled: false })).toBe("unavailable");
    expect(workerHealthState({ worker: "degraded", ready: false })).toBe("unavailable");
    expect(workerHealthState({ worker: "not_configured" })).toBe("not_configured");
    expect(workerHealthState(null)).toBe("unavailable");
  });
});
