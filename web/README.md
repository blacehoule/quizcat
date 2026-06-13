# QuizCat Web

A Next.js rewrite of the QuizCat terminal app, backed by Postgres (Vercel
Postgres / Neon). Single-user, no auth.

## 1. Set up Postgres

1. In your Vercel project, go to **Storage → Create Database → Postgres**
   (this provisions a Neon-backed Postgres database).
2. Copy the connection string Vercel gives you (it auto-populates
   `POSTGRES_URL` as a project env var). For local development, copy it into
   a `.env.local` file in this directory:

   ```
   POSTGRES_URL="postgres://user:password@host/dbname?sslmode=require"
   ```

## 2. Install dependencies

```bash
npm install
```

## 3. Create the schema

```bash
npm run db:migrate
```

This applies `db/schema.sql` (questions, choices, tests, test_questions,
attempts, attempt_answers).

## 4. Seed the question bank

```bash
npm run db:seed
```

This reads `../ccat_full_question_bank_prompt_stimulus.csv` (the same seed
file the Python app uses), validates every row, and upserts questions,
choices, and the 8 sample-exam tests. Safe to re-run.

If your CSV lives somewhere else, pass a path:

```bash
npm run db:seed -- path/to/file.csv
```

## 5. Run locally

```bash
npm run dev
```

Open http://localhost:3000.

## 6. Images

Question images live in `public/images/`, copied from the Python app's
`images/` directory. They're served directly at `/images/<filename>`.

## 7. Deploy to Vercel

1. Push this repo to GitHub (or your git provider of choice).
2. Import the project in Vercel, set the **root directory** to `web/` if
   this lives alongside the Python app.
3. Make sure the Postgres integration from step 1 is attached to the
   project (env vars get injected automatically).
4. After the first deploy, run the migration + seed scripts once against
   the production database — either locally with `POSTGRES_URL` pointed at
   prod, or via `vercel env pull` to fetch the prod connection string into
   `.env.local` temporarily.

## Architecture notes

- `db/schema.sql` — Postgres schema, translated from the original SQLite
  schema in `storage.py`.
- `db/seed.ts` / `db/migrate.ts` — one-off scripts (`tsx`), ported from
  `seed_from_csv` / `create_schema`.
- `lib/db.ts` — shared `pg` connection pool.
- `lib/queries.ts` — data-access layer, ported from `QuizStorage`.
- `lib/questionContent.ts` — question markdown/table formatting, ported from
  `services.py`.
- `app/api/**` — REST endpoints backing the UI (tests, attempts, answers).
- `app/page.tsx`, `app/quiz/[testId]/page.tsx`, `app/stats/page.tsx` — the
  three screens (dashboard, quiz, stats), mirroring `screens.py`.

## Known gaps / follow-ups

- No auth — anyone with the URL can take quizzes and see stats. Fine for
  personal use; add auth before sharing widely.
- The "Abort" button records the attempt as `aborted` server-side but the
  original TUI just discarded it. Adjust `abortQuiz` in
  `components/QuizRunner.tsx` if you'd rather not persist aborted attempts.
