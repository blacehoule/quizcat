"""Application services for QuizCat.

The Textual screens call this module instead of speaking SQLite directly.
That keeps persistence, scoring, and display formatting behind a compact
in-process backend boundary.
"""

from __future__ import annotations

from pathlib import Path

from models import (
    AttemptSummary,
    Question,
    QuestionContent,
    QuizResult,
    SubmittedAnswer,
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

    def list_finished_attempts(self) -> list[AttemptSummary]:
        return self._storage.list_finished_attempts()

    def evaluate_answer(
        self,
        *,
        question: Question,
        question_position: int,
        selected_choice_label: str,
        elapsed_seconds: float,
    ) -> SubmittedAnswer:
        choice = question.choice_for_label(selected_choice_label)
        if choice is None:
            raise ValueError(
                f"Question {question.id} has no choice {selected_choice_label!r}"
            )

        normalized_label = choice.label.upper()
        is_correct = normalized_label == question.correct_choice_label.upper()
        return SubmittedAnswer(
            question_id=question.id,
            question_position=question_position,
            selected_choice_label=normalized_label,
            selected_choice_text=choice.text,
            is_correct=is_correct,
            elapsed_seconds=elapsed_seconds,
        )

    def record_finished_attempt(
        self,
        *,
        test_id: int,
        status: str,
        elapsed_seconds: float,
        total_questions: int,
        answers: tuple[SubmittedAnswer, ...],
    ) -> QuizResult:
        return self._storage.record_finished_attempt(
            test_id=test_id,
            status=status,
            elapsed_seconds=elapsed_seconds,
            total_questions=total_questions,
            answers=answers,
        )

    def question_markdown(self, question: Question) -> str:
        return format_question_markdown(
            question,
            image_asset_dir=self.image_asset_dir,
        )

    def question_content(self, question: Question) -> QuestionContent:
        return format_question_content(
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
    content = format_question_content(
        question,
        image_asset_dir=image_asset_dir,
        include_image_markdown=True,
    )
    return content.markdown


def format_question_content(
    question: Question,
    *,
    image_asset_dir: Path | None = None,
    include_image_markdown: bool = False,
) -> QuestionContent:
    """Build presentation content for a question without mutating the model."""
    parts: list[str] = []
    if question.prompt.strip():
        parts.append(_blockquote(question.prompt.strip()))

    match question.stimulus_type:
        case "image":
            image_path = resolve_image_path(question.stimulus, image_asset_dir)
            if image_path is None:
                parts.append(f"_Image stimulus unavailable: `{question.stimulus}`_")
                return QuestionContent(markdown=_join_markdown_parts(parts))
            if include_image_markdown:
                parts.append(_image_markdown(image_path))
            return QuestionContent(
                markdown=_join_markdown_parts(parts),
                image_path=image_path,
            )
        case "text_table":
            parts.append(f"```\n{question.stimulus}\n```")
        case _:
            parts.append(question.stimulus)

    return QuestionContent(markdown=_join_markdown_parts(parts))


def resolve_image_path(stimulus: str, image_asset_dir: Path | None) -> Path | None:
    """Resolve an image stimulus filename to an existing filesystem path."""
    image_path = Path(stimulus)
    if not image_path.is_absolute() and image_asset_dir is not None:
        image_path = image_asset_dir / image_path

    if not image_path.exists():
        return None

    return image_path


def _blockquote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def _join_markdown_parts(parts: list[str]) -> str:
    return "\n\n".join(part for part in parts if part.strip())


def _image_markdown(image_path: Path) -> str:
    return f"![Question image]({image_path})"
