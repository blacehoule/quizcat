import { NextResponse } from "next/server";
import { createAttempt, getTest, listFinishedAttempts } from "@/lib/queries";

export async function GET() {
  const attempts = await listFinishedAttempts();
  return NextResponse.json(attempts);
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const testId = Number(body?.testId);
  if (!Number.isInteger(testId)) {
    return NextResponse.json({ error: "testId is required" }, { status: 400 });
  }

  const test = await getTest(testId);
  if (!test) {
    return NextResponse.json({ error: "Test not found" }, { status: 404 });
  }

  const attempt = await createAttempt(testId, test.questionCount);
  return NextResponse.json(attempt, { status: 201 });
}
