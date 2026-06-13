import Link from "next/link";
import { listFinishedAttempts } from "@/lib/queries";

export const dynamic = "force-dynamic";

function formatSeconds(seconds: number): string {
  const total = Math.floor(seconds);
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

export default async function StatsPage() {
  const attempts = await listFinishedAttempts();

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-6 py-12">
      <header>
        <h1 className="text-3xl font-bold tracking-tight">Attempt Results</h1>
      </header>

      <section className="rounded-lg border border-zinc-200 dark:border-zinc-800">
        <h2 className="border-b border-zinc-200 px-4 py-2 text-sm font-semibold uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
          Finished Attempts
        </h2>
        {attempts.length === 0 ? (
          <p className="px-4 py-6 text-sm text-zinc-500">No finished attempts yet</p>
        ) : (
          <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
            {attempts.map((attempt) => (
              <li key={attempt.attemptId} className="px-4 py-3 text-sm">
                <span className="font-medium">Test ID: {attempt.testId}</span>{" "}
                — {attempt.testTitle} | Score: {attempt.correctCount} /{" "}
                {attempt.totalQuestions} | Time: {formatSeconds(attempt.elapsedSeconds)}
              </li>
            ))}
          </ul>
        )}
      </section>

      <Link
        href="/"
        className="self-start rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
      >
        View Tests
      </Link>
    </main>
  );
}
