import { NextResponse } from "next/server";
import { getAttempt } from "@/lib/queries";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const attemptId = Number(id);
  if (!Number.isInteger(attemptId)) {
    return NextResponse.json({ error: "Invalid attempt id" }, { status: 400 });
  }

  const attempt = await getAttempt(attemptId);
  if (!attempt) {
    return NextResponse.json({ error: "Attempt not found" }, { status: 404 });
  }
  return NextResponse.json(attempt);
}
