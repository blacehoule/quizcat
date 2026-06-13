// Domain types mirroring models.py.

export interface Choice {
  label: string;
  text: string;
  position: number;
}

/** Question shape sent to the client during a quiz — answer key omitted. */
export interface ClientQuestion {
  id: number;
  externalId: string | null;
  category: string;
  questionType: string;
  prompt: string;
  stimulus: string;
  stimulusType: "text" | "text_table" | "image";
  choices: Choice[];
}

/** Full question row, including the answer key (server-side only). */
export interface Question extends ClientQuestion {
  origin: string;
  sourceExam: string | null;
  sourceFile: string | null;
  sourceCategory: string | null;
  sourceQuestionNumber: string | null;
  correctChoiceLabel: string;
  correctChoiceText: string;
  explanation: string;
}

export interface QuestionContent {
  markdown: string;
  imagePath: string | null;
}

export interface TestSummary {
  id: number;
  title: string;
  kind: string;
  sourceExam: string | null;
  questionCount: number;
  timeLimitSeconds: number;
}

export interface TestDefinition extends TestSummary {
  questions: ClientQuestion[];
}

export interface QuizAttempt {
  id: number;
  testId: number;
  status: "in_progress" | "completed" | "timed_out" | "aborted";
  startedAt: string;
  finishedAt: string | null;
  elapsedSeconds: number;
  answeredCount: number;
  correctCount: number;
  totalQuestions: number;
}

export interface AttemptAnswer {
  id: number;
  attemptId: number;
  questionId: number;
  questionPosition: number;
  selectedChoiceLabel: string;
  selectedChoiceText: string;
  isCorrect: boolean;
  elapsedSeconds: number;
}

/** Response returned after submitting an answer — includes the answer key. */
export interface AnswerResult extends AttemptAnswer {
  correctChoiceLabel: string;
  correctChoiceText: string;
  explanation: string;
}

export interface QuizResult {
  attemptId: number;
  status: string;
  elapsedSeconds: number;
  answeredCount: number;
  correctCount: number;
  totalQuestions: number;
  accuracyPercent: number;
}

export interface AttemptSummary {
  attemptId: number;
  testId: number;
  testTitle: string;
  status: string;
  startedAt: string;
  finishedAt: string | null;
  elapsedSeconds: number;
  answeredCount: number;
  correctCount: number;
  totalQuestions: number;
}
