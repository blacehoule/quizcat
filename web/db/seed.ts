/**
 * Seed the Postgres database from ccat_full_question_bank_prompt_stimulus.csv.
 *
 * Port of storage.py's seed_from_csv / validate_seed_row / _extract_choices /
 * _upsert_question / _replace_choices / _upsert_seed_test /
 * _replace_test_questions / _sort_source_exam.
 *
 * Usage:
 *   npx tsx db/seed.ts [path/to/csv]
 *
 * Requires POSTGRES_URL (or DATABASE_URL) in the environment — load via
 * .env.local with `dotenv/config` or export it in your shell.
 */
import "dotenv/config";
import { readFileSync } from "fs";
import path from "path";
import { parse } from "csv-parse/sync";
import { Pool } from "pg";

const VALID_STIMULUS_TYPES = new Set(["text", "text_table", "image"]);
const CHOICE_LABELS = ["A", "B", "C", "D", "E"] as const;

interface Choice {
  label: string;
  text: string;
  position: number;
}

interface SeedQuestion {
  externalId: string;
  sourceExam: string;
  sourceFile: string;
  sourceCategory: string;
  sourceQuestionNumber: string;
  category: string;
  questionType: string;
  prompt: string;
  stimulus: string;
  stimulusType: string;
  correctChoiceLabel: string;
  correctChoiceText: string;
  explanation: string;
  choices: Choice[];
}

class SeedValidationError extends Error {}

function required(row: Record<string, string>, column: string, label: string): string {
  const value = (row[column] ?? "").trim();
  if (!value) {
    throw new SeedValidationError(`${label}: ${column} is required`);
  }
  return value;
}

function extractChoices(row: Record<string, string>): Choice[] {
  const choices: Choice[] = [];
  CHOICE_LABELS.forEach((label, index) => {
    const text = (row[`choice_${label.toLowerCase()}`] ?? "").trim();
    if (text) {
      choices.push({ label, text, position: index + 1 });
    }
  });
  return choices;
}

function validateSeedRow(row: Record<string, string>, lineNumber: number): SeedQuestion {
  const label = `line ${lineNumber}`;

  const externalId = required(row, "question_id", label);
  const sourceExam = required(row, "source_exam", label);
  const category = required(row, "category", label);
  const questionType = required(row, "question_type", label);
  const stimulusType = required(row, "stimulus_type", label);
  const correctChoiceLabel = required(row, "correct_choice_label", label).toUpperCase();
  const correctChoiceText = required(row, "correct_choice_text", label);

  if (!VALID_STIMULUS_TYPES.has(stimulusType)) {
    throw new SeedValidationError(`${label}: invalid stimulus_type '${stimulusType}'`);
  }

  const prompt = row.prompt ?? "";
  const stimulus = row.stimulus ?? "";
  if (!prompt.trim() && !stimulus.trim()) {
    throw new SeedValidationError(`${label}: prompt or stimulus is required`);
  }

  if (stimulusType === "image") {
    const imageFilename = row.image_filename ?? "";
    if (imageFilename && imageFilename !== stimulus) {
      throw new SeedValidationError(
        `${label}: image_filename must match stimulus for image rows`
      );
    }
  }

  const choices = extractChoices(row);
  if (choices.length === 0) {
    throw new SeedValidationError(`${label}: at least one choice is required`);
  }

  const choiceByLabel = new Map(choices.map((choice) => [choice.label, choice]));
  const correctChoice = choiceByLabel.get(correctChoiceLabel);
  if (!correctChoice) {
    throw new SeedValidationError(`${label}: correct_choice_label is not present in choices`);
  }
  if (correctChoice.text.trim() !== correctChoiceText) {
    throw new SeedValidationError(
      `${label}: correct_choice_text does not match the labeled choice`
    );
  }

  return {
    externalId,
    sourceExam,
    sourceFile: row.source_file ?? "",
    sourceCategory: row.source_category ?? "",
    sourceQuestionNumber: row.source_question_number ?? "",
    category,
    questionType,
    prompt,
    stimulus,
    stimulusType,
    correctChoiceLabel,
    correctChoiceText,
    explanation: row.explanation ?? "",
    choices,
  };
}

function sortSourceExamKey(sourceExam: string): [number, string] {
  return /^\d+$/.test(sourceExam) ? [Number(sourceExam), sourceExam] : [10_000, sourceExam];
}

async function upsertQuestion(pool: Pool, seed: SeedQuestion): Promise<number> {
  await pool.query(
    `INSERT INTO questions (
       external_id, origin, source_exam, source_file, source_category,
       source_question_number, category, question_type, prompt, stimulus,
       stimulus_type, correct_choice_label, correct_choice_text, explanation
     )
     VALUES ($1, 'seed', $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
     ON CONFLICT (external_id) DO UPDATE SET
       origin = excluded.origin,
       source_exam = excluded.source_exam,
       source_file = excluded.source_file,
       source_category = excluded.source_category,
       source_question_number = excluded.source_question_number,
       category = excluded.category,
       question_type = excluded.question_type,
       prompt = excluded.prompt,
       stimulus = excluded.stimulus,
       stimulus_type = excluded.stimulus_type,
       correct_choice_label = excluded.correct_choice_label,
       correct_choice_text = excluded.correct_choice_text,
       explanation = excluded.explanation`,
    [
      seed.externalId,
      seed.sourceExam,
      seed.sourceFile,
      seed.sourceCategory,
      seed.sourceQuestionNumber,
      seed.category,
      seed.questionType,
      seed.prompt,
      seed.stimulus,
      seed.stimulusType,
      seed.correctChoiceLabel,
      seed.correctChoiceText,
      seed.explanation,
    ]
  );
  const { rows } = await pool.query("SELECT id FROM questions WHERE external_id = $1", [
    seed.externalId,
  ]);
  return rows[0].id as number;
}

async function replaceChoices(pool: Pool, questionId: number, choices: Choice[]): Promise<void> {
  await pool.query("DELETE FROM choices WHERE question_id = $1", [questionId]);
  for (const choice of choices) {
    await pool.query(
      `INSERT INTO choices (question_id, label, position, text) VALUES ($1, $2, $3, $4)`,
      [questionId, choice.label, choice.position, choice.text]
    );
  }
}

async function upsertSeedTest(pool: Pool, sourceExam: string, questionCount: number): Promise<number> {
  const title = `Sample Exam ${sourceExam}`;
  await pool.query(
    `INSERT INTO tests (title, kind, source_exam, question_count, time_limit_seconds)
     VALUES ($1, 'source_exam', $2, $3, 900)
     ON CONFLICT (source_exam) DO UPDATE SET
       title = excluded.title,
       kind = excluded.kind,
       question_count = excluded.question_count,
       time_limit_seconds = excluded.time_limit_seconds`,
    [title, sourceExam, questionCount]
  );
  const { rows } = await pool.query("SELECT id FROM tests WHERE source_exam = $1", [sourceExam]);
  return rows[0].id as number;
}

async function replaceTestQuestions(pool: Pool, testId: number, questionIds: number[]): Promise<void> {
  await pool.query("DELETE FROM test_questions WHERE test_id = $1", [testId]);
  for (let i = 0; i < questionIds.length; i++) {
    await pool.query(
      `INSERT INTO test_questions (test_id, question_id, position) VALUES ($1, $2, $3)`,
      [testId, questionIds[i], i + 1]
    );
  }
}

async function main(): Promise<void> {
  const csvPath = process.argv[2] ?? path.resolve(__dirname, "../../ccat_full_question_bank_prompt_stimulus.csv");
  const csvContent = readFileSync(csvPath, "utf-8");
  const records: Record<string, string>[] = parse(csvContent, {
    columns: true,
    skip_empty_lines: true,
  });

  const seedQuestions = records.map((row, index) => validateSeedRow(row, index + 2));

  const pool = new Pool({
    connectionString: process.env.POSTGRES_URL ?? process.env.DATABASE_URL,
  });

  try {
    const questionsByExam = new Map<string, number[]>();

    for (const seed of seedQuestions) {
      const questionId = await upsertQuestion(pool, seed);
      await replaceChoices(pool, questionId, seed.choices);
      const list = questionsByExam.get(seed.sourceExam) ?? [];
      list.push(questionId);
      questionsByExam.set(seed.sourceExam, list);
    }

    const sourceExams = [...questionsByExam.keys()].sort((a, b) => {
      const [aNum, aStr] = sortSourceExamKey(a);
      const [bNum, bStr] = sortSourceExamKey(b);
      if (aNum !== bNum) return aNum - bNum;
      return aStr.localeCompare(bStr);
    });

    for (const sourceExam of sourceExams) {
      const questionIds = questionsByExam.get(sourceExam)!;
      const testId = await upsertSeedTest(pool, sourceExam, questionIds.length);
      await replaceTestQuestions(pool, testId, questionIds);
    }

    console.log(
      `Seeded ${seedQuestions.length} questions across ${sourceExams.length} tests.`
    );
  } finally {
    await pool.end();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
