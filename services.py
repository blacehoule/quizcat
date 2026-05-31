"""Application services for QuizCat.

The Textual screens call this module instead of speaking SQLite directly.
That keeps persistence, scoring, and display formatting behind a compact
in-process backend boundary.
"""

from __future__ import annotations

from pathlib import Path

from models import (
    AttemptAnswer,
    Question,
    QuizAttempt,
    QuizResult,
    TestDefinition,
    TestSummary,
)
from storage import (
    DEFAULT_CSV_PATH,
    DEFAULT_DB_PATH,
    QuizStorage,
    connect_database,
    create_schema,
    seed_from_csv,
)


class QuizService:
    """In-process application service used by the TUI."""

    def __init__(
        self,
        storage: QuizStorage,
        *,
        image_asset_dir: Path | None = None,
    ) -> None:
        self._storage = storage
        self.image_asset_dir = image_asset_dir

    def close(self) -> None:
        self._storage.close()

    def list_tests(self) -> list[TestSummary]:
        return self._storage.list_tests()

    def get_test(self, test_id: int) -> TestDefinition:
        return self._storage.get_test(test_id)

    def start_attempt(self, test_id: int, total_questions: int) -> QuizAttempt:
        return self._storage.create_attempt(test_id, total_questions)

    def submit_answer(
        self,
        *,
        attempt_id: int,
        question: Question,
        question_position: int,
        selected_choice_label: str,
        elapsed_seconds: float,
    ) -> AttemptAnswer:
        choice = question.choice_for_label(selected_choice_label)
        if choice is None:
            raise ValueError(
                f"Question {question.id} has no choice {selected_choice_label!r}"
            )

        normalized_label = choice.label.upper()
        is_correct = normalized_label == question.correct_choice_label.upper()
        return self._storage.record_answer(
            attempt_id=attempt_id,
            question_id=question.id,
            question_position=question_position,
            selected_choice_label=normalized_label,
            selected_choice_text=choice.text,
            is_correct=is_correct,
            elapsed_seconds=elapsed_seconds,
        )

    def finish_attempt(
        self,
        *,
        attempt_id: int,
        status: str,
        elapsed_seconds: float,
        total_questions: int,
    ) -> QuizResult:
        return self._storage.finish_attempt(
            attempt_id=attempt_id,
            status=status,
            elapsed_seconds=elapsed_seconds,
            total_questions=total_questions,
        )

    def abort_attempt(
        self,
        *,
        attempt_id: int,
        elapsed_seconds: float,
        total_questions: int,
    ) -> QuizResult:
        return self.finish_attempt(
            attempt_id=attempt_id,
            status="aborted",
            elapsed_seconds=elapsed_seconds,
            total_questions=total_questions,
        )

    def question_markdown(self, question: Question) -> str:
        return format_question_markdown(
            question,
            image_asset_dir=self.image_asset_dir,
        )


def create_quiz_service(
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    seed_csv_path: Path | str | None = DEFAULT_CSV_PATH,
    image_asset_dir: Path | str | None = None,
) -> QuizService:
    """Create and initialize the default in-process service."""
    connection = connect_database(db_path)
    create_schema(connection)
    if seed_csv_path is not None:
        seed_from_csv(connection, seed_csv_path)

    image_dir = Path(image_asset_dir) if image_asset_dir is not None else None
    return QuizService(QuizStorage(connection), image_asset_dir=image_dir)


def format_question_markdown(
    question: Question,
    *,
    image_asset_dir: Path | None = None,
) -> str:
    """Build the Markdown body for a question without mutating the model."""
    parts: list[str] = []
    if question.prompt.strip():
        parts.append(_blockquote(question.prompt.strip()))

    match question.stimulus_type:
        case "image":
            parts.append(_image_markdown(question.stimulus, image_asset_dir))
        case "text_table":
            parts.append(f"```\n{question.stimulus}\n```")
        case _:
            parts.append(question.stimulus)

    return "\n\n".join(part for part in parts if part.strip())


def _blockquote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def _image_markdown(stimulus: str, image_asset_dir: Path | None) -> str:
    if image_asset_dir is None:
        return f"![Question image]({stimulus})"

    image_path = Path(stimulus)
    if not image_path.is_absolute():
        image_path = image_asset_dir / stimulus

    if not image_path.exists():
        return f"_Image stimulus unavailable: `{stimulus}`_"

    return f"![Question image]({image_path})"
