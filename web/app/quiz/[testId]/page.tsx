import { notFound } from "next/navigation";
import { getTest } from "@/lib/queries";
import QuizRunner from "@/components/QuizRunner";

export const dynamic = "force-dynamic";

export default async function QuizPage({
  params,
}: {
  params: Promise<{ testId: string }>;
}) {
  const { testId } = await params;
  const id = Number(testId);
  if (!Number.isInteger(id)) {
    notFound();
  }

  const test = await getTest(id);
  if (!test) {
    notFound();
  }

  return <QuizRunner test={test} />;
}
