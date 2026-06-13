import type { QueryResultRow } from "pg";
import { getPool } from "./db";
import type {
  AttemptAnswer,
  AttemptSummary,
  Choice,
  Question,
  QuizAttempt,
  QuizResult,
  TestDefinition,
  TestSummary,
} from "./types";

type FinalAttemptStatus = "completed" | "timed_out";
const VALID_FINAL_STATUSES = new Set<string>([
  "completed",
  "timed_out",
  "aborted",
]);

export async function listTests(): Promise<TestSummary[]> {
  const { rows } = await getPool().query(
    `SELECT id, title, kind, source_exam, question_count, time_limit_seconds
     FROM tests
     ORDER BY id`
  );
  return rows.map(testSummaryFromRow);
}

export async function getTest(testId: number): Promise<TestDefinition | null> {
  const testResult = await getPool().query(
    `SELECT id, title, kind, source_exam, question_count, time_limit_seconds
     FROM tests
     WHERE id = $1`,
    [testId]
  );
  const testRow = testResult.rows[0];
  if (!testRow) return null;

  const questionResult = await getPool().query(
    `SELECT q.*
     FROM test_questions tq
     JOIN questions q ON q.id = tq.question_id
     WHERE tq.test_id = $1
     ORDER BY tq.position`,
    [testId]
  );

  const questionIds = questionResult.rows.map((row) => row.id as number);
  const choicesByQuestion = await choicesByQuestionId(questionIds);

  const questions = questionResult.rows.map((row) =>
    questionFromRow(row, choicesByQuestion.get(row.id) ?? [])
  );

  return {
    ...testSummaryFromRow(testRow),
    questions: questions.map((question) => ({
      id: question.id,
      externalId: question.externalId,
      category: question.category,
      questionType: question.questionType,
      prompt: question.prompt,
      stimulus: question.stimulus,
      stimulusType: question.stimulusType,
      choices: question.choices,
    })),
  };
}

/** Full question rows including the answer key — for server-side use only. */
export async function getTestQuestions(testId: number): Promise<Question[]> {
  const questionResult = await getPool().query(
    `SELECT q.*
     FROM test_questions tq
     JOIN questions q ON q.id = tq.question_id
     WHERE tq.test_id = $1
     ORDER BY tq.position`,
    [testId]
  );
  const questionIds = questionResult.rows.map((row) => row.id as number);
  const choicesByQuestion = await choicesByQuestionId(questionIds);
  return questionResult.rows.map((row) =>
    questionFromRow(row, choicesByQuestion.get(row.id) ?? [])
  );
}

export async function getQuestion(questionId: number): Promise<Question | null> {
  const result = await getPool().query(
    `SELECT * FROM questions WHERE id = $1`,
    [questionId]
  );
  const row = result.rows[0];
  if (!row) return null;
  const choicesByQuestion = await choicesByQuestionId([questionId]);
  return questionFromRow(row, choicesByQuestion.get(questionId) ?? []);
}

export async function listFinishedAttempts(): Promise<AttemptSummary[]> {
  const { rows } = await getPool().query(
    `SELECT a.id AS attempt_id,
            a.test_id AS test_id,
            t.title AS test_title,
            a.status AS status,
            a.started_at AS started_at,
            a.finished_at AS finished_at,
            a.elapsed_seconds AS elapsed_seconds,
            a.answered_count AS answered_count,
            a.correct_count AS correct_count,
            a.total_questions AS total_questions
     FROM attempts a
     JOIN tests t ON t.id = a.test_id
     WHERE a.status IN ('completed', 'timed_out')
     ORDER BY a.finished_at DESC, a.id DESC`
  );
  return rows.map(attemptSummaryFromRow);
}

export async function createAttempt(
  testId: number,
  totalQuestions: number
): Promise<QuizAttempt> {
  const { rows } = await getPool().query(
    `INSERT INTO attempts (test_id, status, started_at, total_questions)
     VALUES ($1, 'in_progress', NOW(), $2)
     RETURNING id, test_id, status, started_at, finished_at, elapsed_seconds,
               answered_count, correct_count, total_questions`,
    [testId, totalQuestions]
  );
  return attemptFromRow(rows[0]);
}

export async function getAttempt(attemptId: number): Promise<QuizAttempt | null> {
  const { rows } = await getPool().query(
    `SELECT id, test_id, status, started_at, finished_at, elapsed_seconds,
            answered_count, correct_count, total_questions
     FROM attempts
     WHERE id = $1`,
    [attemptId]
  );
  if (!rows[0]) return null;
  return attemptFromRow(rows[0]);
}

export async function recordAnswer(params: {
  attemptId: number;
  questionId: number;
  questionPosition: number;
  selectedChoiceLabel: string;
  selectedChoiceText: string;
  isCorrect: boolean;
  elapsedSeconds: number;
}): Promise<AttemptAnswer> {
  const pool = getPool();
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const insertResult = await client.query(
      `INSERT INTO attempt_answers (
         attempt_id, question_id, question_position,
         selected_choice_label, selected_choice_text, is_correct, elapsed_seconds
       )
       VALUES ($1, $2, $3, $4, $5, $6, $7)
       ON CONFLICT (attempt_id, question_id) DO UPDATE SET
         question_position = excluded.question_position,
         selected_choice_label = excluded.selected_choice_label,
         selected_choice_text = excluded.selected_choice_text,
         is_correct = excluded.is_correct,
         elapsed_seconds = excluded.elapsed_seconds
       RETURNING id, attempt_id, question_id, question_position,
                 selected_choice_label, selected_choice_text, is_correct, elapsed_seconds`,
      [
        params.attemptId,
        params.questionId,
        params.questionPosition,
        params.selectedChoiceLabel,
        params.selectedChoiceText,
        params.isCorrect,
        params.elapsedSeconds,
      ]
    );

    const counts = await client.query(
      `SELECT COUNT(*) AS answered_count,
              COALESCE(SUM(CASE WHEN is_correct THEN 1 ELSE 0 END), 0) AS correct_count
       FROM attempt_answers
       WHERE attempt_id = $1`,
      [params.attemptId]
    );

    await client.query(
      `UPDATE attempts
       SET elapsed_seconds = $2,
           answered_count = $3,
           correct_count = $4
       WHERE id = $1`,
      [
        params.attemptId,
        params.elapsedSeconds,
        Number(counts.rows[0].answered_count),
        Number(counts.rows[0].correct_count),
      ]
    );

    await client.query("COMMIT");
    return answerFromRow(insertResult.rows[0]);
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}

export async function finishAttempt(params: {
  attemptId: number;
  status: FinalAttemptStatus | "aborted";
  elapsedSeconds: number;
  totalQuestions: number;
}): Promise<QuizResult> {
  if (!VALID_FINAL_STATUSES.has(params.status)) {
    throw new Error(`Invalid final attempt status ${params.status}`);
  }

  const counts = await getPool().query(
    `SELECT COUNT(*) AS answered_count,
            COALESCE(SUM(CASE WHEN is_correct THEN 1 ELSE 0 END), 0) AS correct_count
     FROM attempt_answers
     WHERE attempt_id = $1`,
    [params.attemptId]
  );
  const answeredCount = Number(counts.rows[0].answered_count);
  const correctCount = Number(counts.rows[0].correct_count);

  await getPool().query(
    `UPDATE attempts
     SET status = $2,
         finished_at = NOW(),
         elapsed_seconds = $3,
         answered_count = $4,
         correct_count = $5,
         total_questions = $6
     WHERE id = $1`,
    [
      params.attemptId,
      params.status,
      params.elapsedSeconds,
      answeredCount,
      correctCount,
      params.totalQuestions,
    ]
  );

  return getResult(params.attemptId);
}

export async function getResult(attemptId: number): Promise<QuizResult> {
  const attempt = await getAttempt(attemptId);
  if (!attempt) {
    throw new Error(`Unknown attempt id ${attemptId}`);
  }
  const accuracyPercent =
    attempt.answeredCount === 0
      ? 0
      : (attempt.correctCount / attempt.answeredCount) * 100;
  return {
    attemptId: attempt.id,
    status: attempt.status,
    elapsedSeconds: attempt.elapsedSeconds,
    answeredCount: attempt.answeredCount,
    correctCount: attempt.correctCount,
    totalQuestions: attempt.totalQuestions,
    accuracyPercent,
  };
}

// ---------------------------------------------------------------------------
// Row mapping helpers
// ---------------------------------------------------------------------------

async function choicesByQuestionId(
  questionIds: number[]
): Promise<Map<number, Choice[]>> {
  const map = new Map<number, Choice[]>();
  if (questionIds.length === 0) return map;

  const { rows } = await getPool().query(
    `SELECT question_id, label, position, text
     FROM choices
     WHERE question_id = ANY($1::int[])
     ORDER BY question_id, position`,
    [questionIds]
  );

  for (const id of questionIds) map.set(id, []);
  for (const row of rows) {
    map.get(row.question_id)?.push({
      label: row.label,
      text: row.text,
      position: row.position,
    });
  }
  return map;
}

function testSummaryFromRow(row: QueryResultRow): TestSummary {
  return {
    id: row.id,
    title: row.title,
    kind: row.kind,
    sourceExam: row.source_exam,
    questionCount: row.question_count,
    timeLimitSeconds: row.time_limit_seconds,
  };
}

function questionFromRow(row: QueryResultRow, choices: Choice[]): Question {
  return {
    id: row.id,
    externalId: row.external_id,
    origin: row.origin,
    sourceExam: row.source_exam,
    sourceFile: row.source_file,
    sourceCategory: row.source_category,
    sourceQuestionNumber: row.source_question_number,
    category: row.category,
    questionType: row.question_type,
    prompt: row.prompt,
    stimulus: row.stimulus,
    stimulusType: row.stimulus_type,
    correctChoiceLabel: row.correct_choice_label,
    correctChoiceText: row.correct_choice_text,
    explanation: row.explanation,
    choices,
  };
}

function attemptFromRow(row: QueryResultRow): QuizAttempt {
  return {
    id: row.id,
    testId: row.test_id,
    status: row.status,
    startedAt: toIso(row.started_at),
    finishedAt: row.finished_at ? toIso(row.finished_at) : null,
    elapsedSeconds: Number(row.elapsed_seconds),
    answeredCount: row.answered_count,
    correctCount: row.correct_count,
    totalQuestions: row.total_questions,
  };
}

function answerFromRow(row: QueryResultRow): AttemptAnswer {
  return {
    id: row.id,
    attemptId: row.attempt_id,
    questionId: row.question_id,
    questionPosition: row.question_position,
    selectedChoiceLabel: row.selected_choice_label,
    selectedChoiceText: row.selected_choice_text,
    isCorrect: row.is_correct,
    elapsedSeconds: Number(row.elapsed_seconds),
  };
}

function attemptSummaryFromRow(row: QueryResultRow): AttemptSummary {
  return {
    attemptId: row.attempt_id,
    testId: row.test_id,
    testTitle: row.test_title,
    status: row.status,
    startedAt: toIso(row.started_at),
    finishedAt: row.finished_at ? toIso(row.finished_at) : null,
    elapsedSeconds: Number(row.elapsed_seconds),
    answeredCount: row.answered_count,
    correctCount: row.correct_count,
    totalQuestions: row.total_questions,
  };
}

function toIso(value: string | Date): string {
  return value instanceof Date ? value.toISOString() : value;
}
