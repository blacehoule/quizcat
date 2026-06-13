import { NextResponse } from "next/server";
import { finishAttempt, getAttempt } from "@/lib/queries";

const VALID_STATUSES = new Set(["completed", "timed_out", "aborted"]);

export async function POST(
  request: Request,
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

  const body = await request.json().catch(() => null);
  const status = String(body?.status ?? "");
  const elapsedSeconds = Number(body?.elapsedSeconds);

  if (!VALID_STATUSES.has(status) || !Number.isFinite(elapsedSeconds)) {
    return NextResponse.json({ error: "Invalid finish payload" }, { status: 400 });
  }

  const result = await finishAttempt({
    attemptId,
    status: status as "completed" | "timed_out" | "aborted",
    elapsedSeconds,
    totalQuestions: attempt.totalQuestions,
  });

  return NextResponse.json(result);
}
