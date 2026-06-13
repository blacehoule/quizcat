-- QuizCat Postgres schema (Vercel Postgres / Neon)
-- Translated from the original SQLite schema in storage.py.

CREATE TABLE IF NOT EXISTS questions (
    id SERIAL PRIMARY KEY,
    external_id TEXT UNIQUE,
    origin TEXT NOT NULL,
    source_exam TEXT,
    source_file TEXT,
    source_category TEXT,
    source_question_number TEXT,
    category TEXT NOT NULL,
    question_type TEXT NOT NULL,
    prompt TEXT NOT NULL DEFAULT '',
    stimulus TEXT NOT NULL,
    stimulus_type TEXT NOT NULL
        CHECK (stimulus_type IN ('text', 'text_table', 'image')),
    correct_choice_label TEXT NOT NULL,
    correct_choice_text TEXT NOT NULL,
    explanation TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS choices (
    id SERIAL PRIMARY KEY,
    question_id INTEGER NOT NULL
        REFERENCES questions(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    position INTEGER NOT NULL,
    text TEXT NOT NULL,
    UNIQUE (question_id, label),
    UNIQUE (question_id, position)
);

CREATE TABLE IF NOT EXISTS tests (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    source_exam TEXT UNIQUE,
    question_count INTEGER NOT NULL,
    time_limit_seconds INTEGER NOT NULL DEFAULT 900
);

CREATE TABLE IF NOT EXISTS test_questions (
    test_id INTEGER NOT NULL
        REFERENCES tests(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL
        REFERENCES questions(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    PRIMARY KEY (test_id, question_id),
    UNIQUE (test_id, position)
);

CREATE TABLE IF NOT EXISTS attempts (
    id SERIAL PRIMARY KEY,
    test_id INTEGER NOT NULL REFERENCES tests(id),
    status TEXT NOT NULL
        CHECK (status IN (
            'in_progress',
            'completed',
            'timed_out',
            'aborted'
        )),
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    elapsed_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
    answered_count INTEGER NOT NULL DEFAULT 0,
    correct_count INTEGER NOT NULL DEFAULT 0,
    total_questions INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS attempt_answers (
    id SERIAL PRIMARY KEY,
    attempt_id INTEGER NOT NULL
        REFERENCES attempts(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES questions(id),
    question_position INTEGER NOT NULL,
    selected_choice_label TEXT NOT NULL,
    selected_choice_text TEXT NOT NULL,
    is_correct BOOLEAN NOT NULL,
    elapsed_seconds DOUBLE PRECISION NOT NULL,
    UNIQUE (attempt_id, question_id),
    UNIQUE (attempt_id, question_position)
);

CREATE INDEX IF NOT EXISTS idx_choices_question_position
    ON choices(question_id, position);
CREATE INDEX IF NOT EXISTS idx_test_questions_position
    ON test_questions(test_id, position);
CREATE INDEX IF NOT EXISTS idx_attempt_answers_attempt
    ON attempt_answers(attempt_id, question_position);
