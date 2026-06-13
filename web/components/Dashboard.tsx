"use client";

import { useState } from "react";
import Link from "next/link";
import type { TestSummary } from "@/lib/types";

export default function Dashboard({ tests }: { tests: TestSummary[] }) {
  const [selectedId, setSelectedId] = useState<number | null>(tests[0]?.id ?? null);

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-6 py-12">
      <header>
        <h1 className="text-3xl font-bold tracking-tight">QuizCat</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Timed, CCAT-style multiple-choice practice tests.
        </p>
      </header>

      <section className="rounded-lg border border-zinc-200 dark:border-zinc-800">
        <h2 className="border-b border-zinc-200 px-4 py-2 text-sm font-semibold uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
          Available Exams
        </h2>
        {tests.length === 0 ? (
          <p className="px-4 py-6 text-sm text-zinc-500">
            No exams found. Run the seed script to load the question bank.
          </p>
        ) : (
          <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
            {tests.map((test) => {
              const minutes = Math.floor(test.timeLimitSeconds / 60);
              const isSelected = test.id === selectedId;
              return (
                <li key={test.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(test.id)}
                    className={`flex w-full items-center justify-between px-4 py-3 text-left transition-colors ${
                      isSelected
                        ? "bg-emerald-50 dark:bg-emerald-950/40"
                        : "hover:bg-zinc-50 dark:hover:bg-zinc-900"
                    }`}
                  >
                    <span className="font-medium">{test.title}</span>
                    <span className="text-sm text-zinc-500">
                      {test.questionCount} questions / {minutes} min
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <div className="flex gap-3">
        <Link
          href="/stats"
          className="rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
        >
          View Stats
        </Link>
        {selectedId !== null ? (
          <Link
            href={`/quiz/${selectedId}`}
            className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500"
          >
            Start Quiz
          </Link>
        ) : (
          <span className="rounded-md bg-zinc-300 px-4 py-2 text-sm font-medium text-zinc-500">
            Start Quiz
          </span>
        )}
      </div>
    </main>
  );
}
