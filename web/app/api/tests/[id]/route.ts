import { NextResponse } from "next/server";
import { getTest } from "@/lib/queries";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const testId = Number(id);
  if (!Number.isInteger(testId)) {
    return NextResponse.json({ error: "Invalid test id" }, { status: 400 });
  }

  const test = await getTest(testId);
  if (!test) {
    return NextResponse.json({ error: "Test not found" }, { status: 404 });
  }
  return NextResponse.json(test);
}
