import { afterEach, describe, expect, it } from "vitest";
import { isSameOriginRequest } from "../request-security";

describe("same-origin protection", () => {
  afterEach(() => { delete process.env.NEXT_PUBLIC_APP_URL; });
  it("accepts the forwarded public origin and rejects missing or hostile origins", () => {
    const make = (origin?: string) => new Request("http://internal/api", { headers: {
      host: "internal", "x-forwarded-host": "scout.example", "x-forwarded-proto": "https",
      ...(origin ? { origin } : {}),
    } });
    expect(isSameOriginRequest(make("https://scout.example"))).toBe(true);
    expect(isSameOriginRequest(make("https://attacker.example"))).toBe(false);
    expect(isSameOriginRequest(make())).toBe(false);
  });
  it("prefers the configured application origin", () => {
    process.env.NEXT_PUBLIC_APP_URL = "https://royal-scout.example/";
    const req = new Request("http://internal/api", { headers: { host: "internal", origin: "https://royal-scout.example" } });
    expect(isSameOriginRequest(req)).toBe(true);
  });
});
