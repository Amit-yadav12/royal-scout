import { NextResponse, type NextRequest } from "next/server";
import { createServerClient, type CookieOptions } from "@supabase/ssr";

/** Public dashboard reads stay open; only the administrator ingestion page requires a verified session.
 * Every API route enforces its own authentication/role policy (including GETs).
 */
export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const protectedPage = pathname === "/ingestion" || pathname.startsWith("/ingestion/");
  const alwaysPublic = pathname === "/login" || pathname === "/auth/callback" ||
    pathname.startsWith("/_next/") || pathname === "/favicon.ico" || pathname.startsWith("/api/") ||
    /\.(?:avif|css|gif|ico|jpe?g|js|map|png|svg|webp|woff2?|ttf)$/i.test(pathname);
  if (alwaysPublic || !protectedPage) return NextResponse.next();

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) {
    const destination = request.nextUrl.clone();
    destination.pathname = "/login";
    destination.searchParams.set("next", `${pathname}${request.nextUrl.search}`);
    destination.searchParams.set("setup", "required");
    return NextResponse.redirect(destination);
  }

  let response = NextResponse.next({ request });
  const supabase = createServerClient(url, key, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (cookiesToSet: { name: string; value: string; options: CookieOptions }[]) => {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
      },
    },
  });
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) {
    const destination = request.nextUrl.clone();
    destination.pathname = "/login";
    destination.searchParams.set("next", `${pathname}${request.nextUrl.search}`);
    return NextResponse.redirect(destination);
  }
  response.headers.set("x-royal-scout-auth", "authenticated");
  return response;
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
