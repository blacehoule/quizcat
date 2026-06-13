"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ClientQuestion, QuizResult, TestDefinition } from "@/lib/types";
import Link from "next/link";
import { formatQuestionContent } from "@/lib/questionContent";

function formatSeconds(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

export default function QuizRunner({ test }: { test: TestDefinition }) {
  const router = useRouter();
  const totalQuestions = test.questions.length;
  const timeLimitSeconds = test.timeLimitSeconds;

  const [attemptId, setAttemptId] = useState<number | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null);
  const [answeredCount, setAnsweredCount] = useState(0);
  const [correctCount, setCorrectCount] = useState(0);
  const [paused, setPaused] = useState(false);
  const [showElapsed, setShowElapsed] = useState(false);
  const [ended, setEnded] = useState(false);
  const [endedByTime, setEndedByTime] = useState(false);
  const [result, setResult] = useState<QuizResult | null>(null);
  const [displayElapsed, setDisplayElapsed] = useState(0);

  const startedAtRef = useRef<number | null>(null);
  const elapsedBeforePauseRef = useRef(0);
  const endedRef = useRef(false);

  // Start the attempt and the clock once on mount.
  useEffect(() => {
    let cancelled = false;
    fetch("/api/attempts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ testId: test.id }),
    })
      .then((res) => res.json())
      .then((attempt) => {
        if (!cancelled) setAttemptId(attempt.id);
      })
      .catch(() => {
        /* attempt persistence is best-effort */
      });

    startedAtRef.current = Date.now();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const elapsedSeconds = useCallback((): number => {
    if (startedAtRef.current === null) {
      return elapsedBeforePauseRef.current;
    }
    const liveElapsed =
      elapsedBeforePauseRef.current + (Date.now() - startedAtRef.current) / 1000;
    return Math.min(liveElapsed, timeLimitSeconds);
  }, [timeLimitSeconds]);

  const endQuiz = useCallback(
    (byTime: boolean) => {
      if (endedRef.current) return;
      endedRef.current = true;

      const finalElapsedValue = elapsedSeconds();
      elapsedBeforePauseRef.current = finalElapsedValue;
      startedAtRef.current = null;
      setPaused(false);
      setEnded(true);
      setEndedByTime(byTime);
      setDisplayElapsed(finalElapsedValue);

      const finalElapsed = elapsedBeforePauseRef.current;
      if (attemptId !== null) {
        fetch(`/api/attempts/${attemptId}/finish`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            status: byTime ? "timed_out" : "completed",
            elapsedSeconds: finalElapsed,
          }),
        })
          .then((res) => res.json())
          .then((data: QuizResult) => setResult(data))
          .catch(() => {
            /* best-effort */
          });
      }
    },
    [attemptId, elapsedSeconds]
  );

  // Timer tick.
  useEffect(() => {
    const interval = setInterval(() => {
      if (paused || endedRef.current) return;
      const current = elapsedSeconds();
      setDisplayElapsed(current);
      if (current >= timeLimitSeconds) {
        endQuiz(true);
      }
    }, 250);
    return () => clearInterval(interval);
  }, [paused, elapsedSeconds, timeLimitSeconds, endQuiz]);

  const pauseQuiz = () => {
    if (paused || ended) return;
    const current = elapsedSeconds();
    elapsedBeforePauseRef.current = current;
    startedAtRef.current = null;
    setDisplayElapsed(current);
    setPaused(true);
  };

  const resumeQuiz = () => {
    if (!paused || ended) return;
    startedAtRef.current = Date.now();
    setPaused(false);
  };

  const submitAnswer = async () => {
    if (paused || ended || selectedLabel === null) return;

    const question = test.questions[currentIndex];
    const elapsed = elapsedSeconds();

    if (attemptId !== null) {
      try {
        const res = await fetch(`/api/attempts/${attemptId}/answers`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            questionId: question.id,
            questionPosition: currentIndex + 1,
            selectedChoiceLabel: selectedLabel,
            elapsedSeconds: elapsed,
          }),
        });
        const data = await res.json();
        setAnsweredCount((n) => n + 1);
        if (data.isCorrect) setCorrectCount((n) => n + 1);
      } catch {
        setAnsweredCount((n) => n + 1);
      }
    } else {
      setAnsweredCount((n) => n + 1);
    }

    const nextIndex = currentIndex + 1;
    if (nextIndex >= totalQuestions) {
      endQuiz(false);
      return;
    }

    setCurrentIndex(nextIndex);
    setSelectedLabel(null);
  };

  const abortQuiz = () => {
    if (!ended && attemptId !== null) {
      fetch(`/api/attempts/${attemptId}/finish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status: "aborted",
          elapsedSeconds: elapsedSeconds(),
        }),
      }).catch(() => {});
    }
    router.push("/");
  };

  const elapsed = displayElapsed;
  const timerProgress = timeLimitSeconds ? (elapsed / timeLimitSeconds) * 100 : 100;
  const timerLabel = showElapsed
    ? formatSeconds(elapsed)
    : formatSeconds(Math.ceil(timeLimitSeconds - elapsed));

  const currentQuestion: ClientQuestion | undefined = test.questions[currentIndex];
  const content = currentQuestion ? formatQuestionContent(currentQuestion) : null;

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-4 px-6 py-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">{test.title}</h1>
      </header>

      {/* Timer bar */}
      <div className="rounded-md border border-emerald-600/50 px-3 py-2">
        <div className="mb-1 flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-emerald-600">
          <span>Time</span>
          <span className="font-mono text-sm text-zinc-700 dark:text-zinc-300">
            {timerLabel}
          </span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded bg-zinc-200 dark:bg-zinc-800">
          <div
            className="h-full bg-emerald-600 transition-[width]"
            style={{ width: `${Math.min(100, Math.max(0, timerProgress))}%` }}
          />
        </div>
      </div>

      {/* Progress meter */}
      <div className="rounded-md border border-zinc-300 px-3 py-2 dark:border-zinc-700">
        <div className="mb-1 flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-zinc-500">
          <span>Progress</span>
          <span className="font-mono text-sm text-zinc-700 dark:text-zinc-300">
            {answeredCount} / {totalQuestions}
          </span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded bg-zinc-200 dark:bg-zinc-800">
          <div
            className="h-full bg-zinc-500 transition-[width]"
            style={{ width: `${(answeredCount / totalQuestions) * 100}%` }}
          />
        </div>
      </div>

      {/* Content panel */}
      {paused && !ended ? (
        <div className="flex flex-1 items-center justify-center rounded-md border border-zinc-300 py-24 text-2xl font-semibold dark:border-zinc-700">
          Paused ||
        </div>
      ) : ended ? (
        <SummaryPanel
          answered={result?.answeredCount ?? answeredCount}
          correct={result?.correctCount ?? correctCount}
          total={totalQuestions}
          elapsedSeconds={result?.elapsedSeconds ?? elapsed}
          endedByTime={endedByTime}
        />
      ) : (
        <div className="grid flex-1 grid-cols-1 gap-4 md:grid-cols-[2fr_1fr]">
          <div className="rounded-md border border-zinc-300 p-4 dark:border-zinc-700">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Question
            </h2>
            <div className="prose prose-sm dark:prose-invert max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {content?.markdown ?? ""}
              </ReactMarkdown>
            </div>
            {content?.imagePath ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={content.imagePath}
                alt="Question stimulus"
                className="mt-3 max-w-full rounded border border-zinc-200 dark:border-zinc-800"
              />
            ) : null}
          </div>
          <div className="rounded-md border border-zinc-300 p-4 dark:border-zinc-700">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Choices
            </h2>
            <ul className="flex flex-col gap-2">
              {currentQuestion?.choices.map((choice) => {
                const isSelected = choice.label === selectedLabel;
                return (
                  <li key={choice.label}>
                    <button
                      type="button"
                      onClick={() => setSelectedLabel(choice.label)}
                      className={`w-full rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                        isSelected
                          ? "border-emerald-600 bg-emerald-50 dark:bg-emerald-950/40"
                          : "border-zinc-300 hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
                      }`}
                    >
                      <span className="font-semibold">{choice.label}.</span>{" "}
                      {choice.text}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      )}

      {/* Control panel */}
      <div className="flex flex-wrap items-center gap-3 border-t border-zinc-200 pt-4 dark:border-zinc-800">
        {!ended && (
          <>
            {!paused ? (
              <button
                type="button"
                onClick={pauseQuiz}
                className="rounded-md bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-400"
              >
                Pause
              </button>
            ) : (
              <button
                type="button"
                onClick={resumeQuiz}
                className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500"
              >
                Resume
              </button>
            )}
            <button
              type="button"
              onClick={abortQuiz}
              className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500"
            >
              Abort
            </button>
            <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
              <span>Elapsed</span>
              <input
                type="checkbox"
                checked={showElapsed}
                onChange={(e) => setShowElapsed(e.target.checked)}
              />
            </label>
            <button
              type="button"
              onClick={submitAnswer}
              disabled={paused || selectedLabel === null}
              className="ml-auto rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Submit
            </button>
          </>
        )}
        {ended && (
          <Link
            href="/"
            className="ml-auto rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500"
          >
            Dashboard
          </Link>
        )}
      </div>
    </main>
  );
}

function SummaryPanel({
  answered,
  correct,
  total,
  elapsedSeconds,
  endedByTime,
}: {
  answered: number;
  correct: number;
  total: number;
  elapsedSeconds: number;
  endedByTime: boolean;
}) {
  const accuracy = answered ? Math.round((correct / answered) * 100) : 0;
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 rounded-md border border-zinc-300 py-16 dark:border-zinc-700">
      <h2 className="text-2xl font-bold">
        {endedByTime ? "Time Expired" : "Quiz Complete"}
      </h2>
      <p className="text-lg">
        Score: {correct} / {total}
      </p>
      <p className="text-zinc-500">
        Submitted: {answered} / {total}
      </p>
      <p className="text-zinc-500">Time Used: {formatSeconds(elapsedSeconds)}</p>
      <p className="text-zinc-500">Accuracy: {accuracy}%</p>
    </div>
  );
}
