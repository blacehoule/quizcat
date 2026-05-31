"""SQLite storage and seed import for QuizCat."""

from __future__ import annotations

import csv
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from models import (
    AttemptAnswer,
    Choice,
    Question,
    QuizAttempt,
    QuizResult,
    TestDefinition,
    TestSummary,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DB_PATH = PROJECT_ROOT / "var" / "quizcat.sqlite3"
DEFAULT_CSV_PATH = PROJECT_ROOT / "ccat_full_question_bank_prompt_stimulus.csv"

VALID_STIMULUS_TYPES = frozenset({"text", "text_table", "image"})
VALID_ATTEMPT_STATUSES = frozenset(
    {"in_progress", "completed", "timed_out", "aborted"}
)


class SeedValidationError(ValueError):
    """Raised when the seed CSV contains an invalid row."""


@dataclass(frozen=True)
class SeedQuestion:
    """Validated seed-row payload ready for insertion."""

    external_id: str
    source_exam: str
    source_file: str
    source_category: str
    source_question_number: str
    category: str
    question_type: str
    prompt: str
    stimulus: str
    stimulus_type: str
    correct_choice_label: str
    correct_choice_text: str
    explanation: str
    choices: tuple[Choice, ...]


def connect_database(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a SQLite connection with QuizCat defaults."""
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_schema(connection: sqlite3.Connection) -> None:
    """Create the v1 database schema if it is not already present."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY,
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
            id INTEGER PRIMARY KEY,
            question_id INTEGER NOT NULL
                REFERENCES questions(id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            position INTEGER NOT NULL,
            text TEXT NOT NULL,
            UNIQUE (question_id, label),
            UNIQUE (question_id, position)
        );

        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY,
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
            id INTEGER PRIMARY KEY,
            test_id INTEGER NOT NULL REFERENCES tests(id),
            status TEXT NOT NULL
                CHECK (status IN (
                    'in_progress',
                    'completed',
                    'timed_out',
                    'aborted'
                )),
            started_at TEXT NOT NULL,
            finished_at TEXT,
            elapsed_seconds REAL NOT NULL DEFAULT 0,
            answered_count INTEGER NOT NULL DEFAULT 0,
            correct_count INTEGER NOT NULL DEFAULT 0,
            total_questions INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS attempt_answers (
            id INTEGER PRIMARY KEY,
            attempt_id INTEGER NOT NULL
                REFERENCES attempts(id) ON DELETE CASCADE,
            question_id INTEGER NOT NULL REFERENCES questions(id),
            question_position INTEGER NOT NULL,
            selected_choice_label TEXT NOT NULL,
            selected_choice_text TEXT NOT NULL,
            is_correct INTEGER NOT NULL CHECK (is_correct IN (0, 1)),
            elapsed_seconds REAL NOT NULL,
            UNIQUE (attempt_id, question_id),
            UNIQUE (attempt_id, question_position)
        );

        CREATE INDEX IF NOT EXISTS idx_choices_question_position
            ON choices(question_id, position);
        CREATE INDEX IF NOT EXISTS idx_test_questions_position
            ON test_questions(test_id, position);
        CREATE INDEX IF NOT EXISTS idx_attempt_answers_attempt
            ON attempt_answers(attempt_id, question_position);

        PRAGMA user_version = 1;
        """
    )
    connection.commit()


def seed_from_csv(
    connection: sqlite3.Connection,
    csv_path: Path | str = DEFAULT_CSV_PATH,
) -> None:
    """Import the seed CSV into normalized SQLite tables idempotently."""
    seed_questions = _read_seed_questions(Path(csv_path))
    questions_by_exam: dict[str, list[int]] = defaultdict(list)

    with connection:
        for seed_question in seed_questions:
            question_id = _upsert_question(connection, seed_question)
            _replace_choices(connection, question_id, seed_question.choices)
            questions_by_exam[seed_question.source_exam].append(question_id)

        for source_exam in sorted(questions_by_exam, key=_sort_source_exam):
            question_ids = questions_by_exam[source_exam]
            test_id = _upsert_seed_test(connection, source_exam, len(question_ids))
            _replace_test_questions(connection, test_id, question_ids)


def validate_seed_row(
    row: dict[str, str],
    *,
    line_number: int | None = None,
) -> SeedQuestion:
    """Validate and normalize one seed CSV row."""
    row_label = f"line {line_number}" if line_number else "seed row"

    external_id = _required(row, "question_id", row_label)
    source_exam = _required(row, "source_exam", row_label)
    category = _required(row, "category", row_label)
    question_type = _required(row, "question_type", row_label)
    stimulus_type = _required(row, "stimulus_type", row_label)
    correct_choice_label = _required(row, "correct_choice_label", row_label).upper()
    correct_choice_text = _required(row, "correct_choice_text", row_label)

    if stimulus_type not in VALID_STIMULUS_TYPES:
        raise SeedValidationError(
            f"{row_label}: invalid stimulus_type {stimulus_type!r}"
        )

    prompt = row.get("prompt", "")
    stimulus = row.get("stimulus", "")
    if not prompt.strip() and not stimulus.strip():
        raise SeedValidationError(f"{row_label}: prompt or stimulus is required")

    if stimulus_type == "image":
        image_filename = row.get("image_filename", "")
        if image_filename and image_filename != stimulus:
            raise SeedValidationError(
                f"{row_label}: image_filename must match stimulus for image rows"
            )

    choices = _extract_choices(row)
    if not choices:
        raise SeedValidationError(f"{row_label}: at least one choice is required")

    choice_by_label = {choice.label: choice for choice in choices}
    if correct_choice_label not in choice_by_label:
        raise SeedValidationError(
            f"{row_label}: correct_choice_label is not present in choices"
        )
    if choice_by_label[correct_choice_label].text.strip() != correct_choice_text:
        raise SeedValidationError(
            f"{row_label}: correct_choice_text does not match the labeled choice"
        )

    return SeedQuestion(
        external_id=external_id,
        source_exam=source_exam,
        source_file=row.get("source_file", ""),
        source_category=row.get("source_category", ""),
        source_question_number=row.get("source_question_number", ""),
        category=category,
        question_type=question_type,
        prompt=prompt,
        stimulus=stimulus,
        stimulus_type=stimulus_type,
        correct_choice_label=correct_choice_label,
        correct_choice_text=correct_choice_text,
        explanation=row.get("explanation", ""),
        choices=tuple(choices),
    )


class QuizStorage:
    """Repository-style wrapper around a QuizCat SQLite connection."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def close(self) -> None:
        self.connection.close()

    def list_tests(self) -> list[TestSummary]:
        rows = self.connection.execute(
            """
            SELECT id, title, kind, source_exam, question_count, time_limit_seconds
            FROM tests
            ORDER BY id
            """
        ).fetchall()
        return [_test_summary_from_row(row) for row in rows]

    def get_test(self, test_id: int) -> TestDefinition:
        test_row = self.connection.execute(
            """
            SELECT id, title, kind, source_exam, question_count, time_limit_seconds
            FROM tests
            WHERE id = ?
            """,
            (test_id,),
        ).fetchone()
        if test_row is None:
            raise KeyError(f"Unknown test id {test_id}")

        question_rows = self.connection.execute(
            """
            SELECT q.*
            FROM test_questions tq
            JOIN questions q ON q.id = tq.question_id
            WHERE tq.test_id = ?
            ORDER BY tq.position
            """,
            (test_id,),
        ).fetchall()
        choices_by_question = self._choices_by_question_id(
            row["id"] for row in question_rows
        )
        questions = tuple(
            _question_from_row(row, choices_by_question[row["id"]])
            for row in question_rows
        )

        return TestDefinition(
            id=test_row["id"],
            title=test_row["title"],
            kind=test_row["kind"],
            source_exam=test_row["source_exam"],
            question_count=test_row["question_count"],
            time_limit_seconds=test_row["time_limit_seconds"],
            questions=questions,
        )

    def create_attempt(self, test_id: int, total_questions: int) -> QuizAttempt:
        started_at = _utc_now()
        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO attempts (
                    test_id,
                    status,
                    started_at,
                    total_questions
                )
                VALUES (?, 'in_progress', ?, ?)
                """,
                (test_id, started_at, total_questions),
            )
        return self.get_attempt(cursor.lastrowid)

    def get_attempt(self, attempt_id: int) -> QuizAttempt:
        row = self.connection.execute(
            """
            SELECT id, test_id, status, started_at, finished_at, elapsed_seconds,
                   answered_count, correct_count, total_questions
            FROM attempts
            WHERE id = ?
            """,
            (attempt_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown attempt id {attempt_id}")
        return _attempt_from_row(row)

    def record_answer(
        self,
        *,
        attempt_id: int,
        question_id: int,
        question_position: int,
        selected_choice_label: str,
        selected_choice_text: str,
        is_correct: bool,
        elapsed_seconds: float,
    ) -> AttemptAnswer:
        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO attempt_answers (
                    attempt_id,
                    question_id,
                    question_position,
                    selected_choice_label,
                    selected_choice_text,
                    is_correct,
                    elapsed_seconds
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    question_id,
                    question_position,
                    selected_choice_label,
                    selected_choice_text,
                    1 if is_correct else 0,
                    elapsed_seconds,
                ),
            )
            self._refresh_attempt_counts(attempt_id, elapsed_seconds)

        return self.get_answer(cursor.lastrowid)

    def get_answer(self, answer_id: int) -> AttemptAnswer:
        row = self.connection.execute(
            """
            SELECT id, attempt_id, question_id, question_position,
                   selected_choice_label, selected_choice_text, is_correct,
                   elapsed_seconds
            FROM attempt_answers
            WHERE id = ?
            """,
            (answer_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown attempt answer id {answer_id}")
        return _answer_from_row(row)

    def finish_attempt(
        self,
        *,
        attempt_id: int,
        status: str,
        elapsed_seconds: float,
        total_questions: int,
    ) -> QuizResult:
        if status not in VALID_ATTEMPT_STATUSES - {"in_progress"}:
            raise ValueError(f"Invalid final attempt status {status!r}")

        answered_count, correct_count = self._answer_counts(attempt_id)
        with self.connection:
            self.connection.execute(
                """
                UPDATE attempts
                SET status = ?,
                    finished_at = ?,
                    elapsed_seconds = ?,
                    answered_count = ?,
                    correct_count = ?,
                    total_questions = ?
                WHERE id = ?
                """,
                (
                    status,
                    _utc_now(),
                    elapsed_seconds,
                    answered_count,
                    correct_count,
                    total_questions,
                    attempt_id,
                ),
            )
        return self.get_result(attempt_id)

    def get_result(self, attempt_id: int) -> QuizResult:
        attempt = self.get_attempt(attempt_id)
        return QuizResult(
            attempt_id=attempt.id,
            status=attempt.status,
            elapsed_seconds=attempt.elapsed_seconds,
            answered_count=attempt.answered_count,
            correct_count=attempt.correct_count,
            total_questions=attempt.total_questions,
        )

    def _choices_by_question_id(
        self,
        question_ids: Iterable[int],
    ) -> dict[int, tuple[Choice, ...]]:
        ids = tuple(question_ids)
        if not ids:
            return {}

        placeholders = ", ".join("?" for _ in ids)
        rows = self.connection.execute(
            f"""
            SELECT question_id, label, position, text
            FROM choices
            WHERE question_id IN ({placeholders})
            ORDER BY question_id, position
            """,
            ids,
        ).fetchall()

        choices: dict[int, list[Choice]] = {question_id: [] for question_id in ids}
        for row in rows:
            choices[row["question_id"]].append(
                Choice(
                    label=row["label"],
                    text=row["text"],
                    position=row["position"],
                )
            )
        return {
            question_id: tuple(question_choices)
            for question_id, question_choices in choices.items()
        }

    def _refresh_attempt_counts(
        self,
        attempt_id: int,
        elapsed_seconds: float,
    ) -> None:
        answered_count, correct_count = self._answer_counts(attempt_id)
        self.connection.execute(
            """
            UPDATE attempts
            SET elapsed_seconds = ?,
                answered_count = ?,
                correct_count = ?
            WHERE id = ?
            """,
            (elapsed_seconds, answered_count, correct_count, attempt_id),
        )

    def _answer_counts(self, attempt_id: int) -> tuple[int, int]:
        row = self.connection.execute(
            """
            SELECT COUNT(*) AS answered_count,
                   COALESCE(SUM(is_correct), 0) AS correct_count
            FROM attempt_answers
            WHERE attempt_id = ?
            """,
            (attempt_id,),
        ).fetchone()
        return int(row["answered_count"]), int(row["correct_count"])


def _read_seed_questions(csv_path: Path) -> list[SeedQuestion]:
    with csv_path.open(newline="") as seed_file:
        reader = csv.DictReader(seed_file)
        return [
            validate_seed_row(row, line_number=reader.line_num)
            for row in reader
        ]


def _required(row: dict[str, str], column: str, row_label: str) -> str:
    value = row.get(column, "")
    if not value.strip():
        raise SeedValidationError(f"{row_label}: {column} is required")
    return value.strip()


def _extract_choices(row: dict[str, str]) -> list[Choice]:
    choices: list[Choice] = []
    for position, label in enumerate(("A", "B", "C", "D", "E"), start=1):
        text = row.get(f"choice_{label.lower()}", "").strip()
        if text:
            choices.append(Choice(label=label, text=text, position=position))
    return choices


def _upsert_question(
    connection: sqlite3.Connection,
    seed_question: SeedQuestion,
) -> int:
    connection.execute(
        """
        INSERT INTO questions (
            external_id,
            origin,
            source_exam,
            source_file,
            source_category,
            source_question_number,
            category,
            question_type,
            prompt,
            stimulus,
            stimulus_type,
            correct_choice_label,
            correct_choice_text,
            explanation
        )
        VALUES (?, 'seed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(external_id) DO UPDATE SET
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
            explanation = excluded.explanation
        """,
        (
            seed_question.external_id,
            seed_question.source_exam,
            seed_question.source_file,
            seed_question.source_category,
            seed_question.source_question_number,
            seed_question.category,
            seed_question.question_type,
            seed_question.prompt,
            seed_question.stimulus,
            seed_question.stimulus_type,
            seed_question.correct_choice_label,
            seed_question.correct_choice_text,
            seed_question.explanation,
        ),
    )
    row = connection.execute(
        "SELECT id FROM questions WHERE external_id = ?",
        (seed_question.external_id,),
    ).fetchone()
    return int(row["id"])


def _replace_choices(
    connection: sqlite3.Connection,
    question_id: int,
    choices: tuple[Choice, ...],
) -> None:
    connection.execute("DELETE FROM choices WHERE question_id = ?", (question_id,))
    connection.executemany(
        """
        INSERT INTO choices (question_id, label, position, text)
        VALUES (?, ?, ?, ?)
        """,
        (
            (question_id, choice.label, choice.position, choice.text)
            for choice in choices
        ),
    )


def _upsert_seed_test(
    connection: sqlite3.Connection,
    source_exam: str,
    question_count: int,
) -> int:
    title = f"Sample Exam {source_exam}"
    connection.execute(
        """
        INSERT INTO tests (
            title,
            kind,
            source_exam,
            question_count,
            time_limit_seconds
        )
        VALUES (?, 'source_exam', ?, ?, 900)
        ON CONFLICT(source_exam) DO UPDATE SET
            title = excluded.title,
            kind = excluded.kind,
            question_count = excluded.question_count,
            time_limit_seconds = excluded.time_limit_seconds
        """,
        (title, source_exam, question_count),
    )
    row = connection.execute(
        "SELECT id FROM tests WHERE source_exam = ?",
        (source_exam,),
    ).fetchone()
    return int(row["id"])


def _replace_test_questions(
    connection: sqlite3.Connection,
    test_id: int,
    question_ids: list[int],
) -> None:
    connection.execute("DELETE FROM test_questions WHERE test_id = ?", (test_id,))
    connection.executemany(
        """
        INSERT INTO test_questions (test_id, question_id, position)
        VALUES (?, ?, ?)
        """,
        (
            (test_id, question_id, position)
            for position, question_id in enumerate(question_ids, start=1)
        ),
    )


def _sort_source_exam(source_exam: str) -> tuple[int, str]:
    if source_exam.isdigit():
        return int(source_exam), source_exam
    return 10_000, source_exam


def _test_summary_from_row(row: sqlite3.Row) -> TestSummary:
    return TestSummary(
        id=row["id"],
        title=row["title"],
        kind=row["kind"],
        source_exam=row["source_exam"],
        question_count=row["question_count"],
        time_limit_seconds=row["time_limit_seconds"],
    )


def _question_from_row(row: sqlite3.Row, choices: tuple[Choice, ...]) -> Question:
    return Question(
        id=row["id"],
        external_id=row["external_id"],
        origin=row["origin"],
        source_exam=row["source_exam"],
        source_file=row["source_file"],
        source_category=row["source_category"],
        source_question_number=row["source_question_number"],
        category=row["category"],
        question_type=row["question_type"],
        prompt=row["prompt"],
        stimulus=row["stimulus"],
        stimulus_type=row["stimulus_type"],
        correct_choice_label=row["correct_choice_label"],
        correct_choice_text=row["correct_choice_text"],
        explanation=row["explanation"],
        choices=choices,
    )


def _attempt_from_row(row: sqlite3.Row) -> QuizAttempt:
    return QuizAttempt(
        id=row["id"],
        test_id=row["test_id"],
        status=row["status"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        elapsed_seconds=row["elapsed_seconds"],
        answered_count=row["answered_count"],
        correct_count=row["correct_count"],
        total_questions=row["total_questions"],
    )


def _answer_from_row(row: sqlite3.Row) -> AttemptAnswer:
    return AttemptAnswer(
        id=row["id"],
        attempt_id=row["attempt_id"],
        question_id=row["question_id"],
        question_position=row["question_position"],
        selected_choice_label=row["selected_choice_label"],
        selected_choice_text=row["selected_choice_text"],
        is_correct=bool(row["is_correct"]),
        elapsed_seconds=row["elapsed_seconds"],
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
