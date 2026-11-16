import { NextResponse, type NextRequest } from "next/server";

/**
 * Royal Scout's dashboard is intentionally public and read-only.
 * Mutating APIs (uploads, queue/retry, invitations) keep their own session and
 * role checks; never rely on middleware alone to protect an API operation.
 */
export function middleware(request: NextRequest) {
  if (request.nextUrl.pathname === "/login") {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
