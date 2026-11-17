/** Same-origin protection for cookie-authenticated state changes. */
export function isSameOriginRequest(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  try {
    const configured = process.env.NEXT_PUBLIC_APP_URL?.trim();
    const host = request.headers.get("x-forwarded-host")?.split(",")[0]?.trim() || request.headers.get("host");
    const protocol = request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim();
    const expected = configured || (host ? `${protocol || new URL(request.url).protocol.replace(":", "")}://${host}` : new URL(request.url).origin);
    return new URL(origin).origin === new URL(expected).origin;
  } catch {
    return false;
  }
}
