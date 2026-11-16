/**
 * Supabase wiring.
 *
 * The dashboard is fully functional as a read-only analytical viewer without
 * Supabase (the bundle is a build artefact). When Supabase env vars are present,
 * authentication is enforced by `middleware.ts` and the service-role client is
 * available to server-only code for signed uploads and metadata writes.
 *
 * The service-role key is never imported into a client component: this module is
 * only imported from server files / route handlers.
 */
export function supabaseConfig() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const publishable = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  return {
    url: url ?? null,
    publishable: publishable ?? null,
    configured: Boolean(url && publishable),
    serverConfigured: Boolean(url && (process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY)),
  };
}

/** Headers for privileged server-side REST/Storage calls. Never use a user's JWT here. */
export function supabaseServerHeaders(extra: Record<string, string> = {}) {
  const key = (process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY || "").trim();
  if (!key || key.startsWith("sb_publishable_")) throw new Error("A private Supabase server key is required.");
  const isSecret = /^sb_secret_.+$/.test(key);
  const isLegacyJwt = /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(key);
  if (!isSecret && !isLegacyJwt) throw new Error("Supabase server key is malformed.");
  const headers: Record<string, string> = { apikey: key, "Content-Type": "application/json", ...extra };
  if (isLegacyJwt) headers.Authorization = `Bearer ${key}`;
  return headers;
}

export async function createServerSupabase() {
  const { url, publishable } = supabaseConfig();
  if (!url || !publishable) return null;
  const { createServerClient } = await import("@supabase/ssr");
  const { cookies } = await import("next/headers");
  const store = await cookies();
  return createServerClient(url, publishable, {
    cookies: {
      getAll: () => store.getAll(),
      setAll: (list: { name: string; value: string; options?: Record<string, unknown> }[]) => {
        try {
          list.forEach(({ name, value, options }) => store.set(name, value, options));
        } catch {
          /* called from a Server Component: cookie writes are handled by middleware */
        }
      },
    },
  });
}
