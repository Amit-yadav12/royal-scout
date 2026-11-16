import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Legacy endpoint intentionally disabled. File bytes must never pass through a
 * Vercel Function: use /api/uploads/sign, upload directly to private Storage,
 * then POST the storage object references to /api/jobs.
 */
export async function POST() {
  return NextResponse.json(
    {
      error: "This upload endpoint has been retired.",
      hint: "Use the signed direct-to-storage upload flow. It avoids Vercel's 4.5 MB function payload limit.",
    },
    { status: 410 },
  );
}
