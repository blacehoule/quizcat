import { NextResponse } from "next/server";
import { listTests } from "@/lib/queries";

export async function GET() {
  const tests = await listTests();
  return NextResponse.json(tests);
}
