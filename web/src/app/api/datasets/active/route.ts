import { NextResponse } from "next/server";
import { getSuccessfulDatasetOptions } from "@/lib/server-dataset";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const ACTIVE_COOKIE = "rs_active_dataset";

export async function POST(request: Request) {
  let datasetId: unknown;
  try {
    ({ dataset_id: datasetId } = await request.json());
  } catch {
    return NextResponse.json({ error: "Expected a dataset_id or null for the latest successful dataset." }, { status: 400 });
  }
  if (datasetId !== null && (typeof datasetId !== "string" || !/^[A-Za-z0-9_-]{1,64}$/.test(datasetId))) {
    return NextResponse.json({ error: "Invalid dataset identifier." }, { status: 400 });
  }
  try {
    if (datasetId !== null) {
      const available = await getSuccessfulDatasetOptions();
      if (!available.some((item) => item.dataset_id === datasetId)) {
        return NextResponse.json({ error: "That dataset is not a successfully processed dataset in this project." }, { status: 404 });
      }
    }
    const response = NextResponse.json({ selected_id: datasetId, message: "Dataset selection saved." }, { headers: { "Cache-Control": "no-store" } });
    response.cookies.set(ACTIVE_COOKIE, datasetId ?? "", {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: datasetId === null ? 0 : 60 * 60 * 24 * 365,
    });
    return response;
  } catch (cause) {
    return NextResponse.json({ error: cause instanceof Error ? cause.message : "Could not validate dataset history." }, { status: 503 });
  }
}
