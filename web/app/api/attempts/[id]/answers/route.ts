import { NextResponse } from "next/server";
import { getAttempt, getQuestion, recordAnswer } from "@/lib/queries";

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
  const questionId = Number(body?.questionId);
  const questionPosition = Number(body?.questionPosition);
  const selectedChoiceLabel = String(body?.selectedChoiceLabel ?? "");
  const elapsedSeconds = Number(body?.elapsedSeconds);

  if (
    !Number.isInteger(questionId) ||
    !Number.isInteger(questionPosition) ||
    !selectedChoiceLabel ||
    !Number.isFinite(elapsedSeconds)
  ) {
    return NextResponse.json({ error: "Invalid answer payload" }, { status: 400 });
  }

  const question = await getQuestion(questionId);
  if (!question) {
    return NextResponse.json({ error: "Question not found" }, { status: 404 });
  }

  const normalizedLabel = selectedChoiceLabel.toUpperCase();
  const choice = question.choices.find((c) => c.label.toUpperCase() === normalizedLabel);
  if (!choice) {
    return NextResponse.json(
      { error: `Question ${questionId} has no choice ${selectedChoiceLabel}` },
      { status: 400 }
    );
  }

  const isCorrect = normalizedLabel === question.correctChoiceLabel.toUpperCase();

  const answer = await recordAnswer({
    attemptId,
    questionId,
    questionPosition,
    selectedChoiceLabel: normalizedLabel,
    selectedChoiceText: choice.text,
    isCorrect,
    elapsedSeconds,
  });

  return NextResponse.json({
    ...answer,
    correctChoiceLabel: question.correctChoiceLabel,
    correctChoiceText: question.correctChoiceText,
    explanation: question.explanation,
  });
}
