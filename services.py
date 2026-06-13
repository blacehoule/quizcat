"""Application services for QuizCat.

The Textual screens call this module instead of speaking SQLite directly.
That keeps persistence, scoring, and display formatting behind a compact
in-process backend boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harness import (
    ChatClient,
    GenerationRequest,
    HarnessQuestionTrace,
    HarnessRunSummary,
    ProgressCallback,
    create_chat_client,
    run_generation,
)
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


GENERATED_SECONDS_PER_QUESTION = 60


@dataclass(frozen=True)
class GeneratedTestResult:
    """Outcome of a generate-test request, for the UI to react to."""

    test_id: int | None
    run_id: int
    summary: HarnessRunSummary

    @property
    def succeeded(self) -> bool:
        return self.test_id is not None


class QuizService:
    """In-process application service used by the TUI."""

    def __init__(
        self,
        storage: QuizStorage,
        *,
        image_asset_dir: Path | None = None,
        db_path: Path | str | None = None,
    ) -> None:
        self._storage = storage
        self.image_asset_dir = image_asset_dir
        # SQLite connections are single-thread; the db path lets a background
        # worker open its own connection to the same file (see ``generate_test``
        # callers in the TUI). ``None`` for in-memory/test services.
        self.db_path = db_path

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

    def generate_test(
        self,
        *,
        request: GenerationRequest | None = None,
        client: ChatClient | None = None,
        on_question: ProgressCallback | None = None,
    ) -> GeneratedTestResult:
        """Generate a mixed exam via the harness and persist it atomically.

        On success a playable ``generated`` test is created and its run trace
        stored; on failure no test is created but the run trace is still
        recorded so the failure remains observable.
        """
        request = request or GenerationRequest()
        if client is None:
            client = create_chat_client()

        summary = run_generation(client, self._storage, request, on_question=on_question)
        run = _run_to_dict(summary)

        if not summary.accepted:
            run_id = self._storage.record_harness_run(run)
            return GeneratedTestResult(test_id=None, run_id=run_id, summary=summary)

        title = self._next_generated_title()
        time_limit = max(
            GENERATED_SECONDS_PER_QUESTION,
            len(summary.accepted) * GENERATED_SECONDS_PER_QUESTION,
        )
        test_id, run_id = self._storage.create_generated_test(
            title=title,
            time_limit_seconds=time_limit,
            drafts=summary.accepted,
            run=run,
        )
        return GeneratedTestResult(test_id=test_id, run_id=run_id, summary=summary)

    def _next_generated_title(self) -> str:
        generated = sum(1 for test in self.list_tests() if test.kind == "generated")
        return f"Generated Exam {generated + 1}"

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
    stored_db_path = None if str(db_path) == ":memory:" else db_path
    return QuizService(
        QuizStorage(connection), image_asset_dir=image_dir, db_path=stored_db_path
    )


def _run_to_dict(summary: HarnessRunSummary) -> dict:
    """Flatten a run summary into the primitive shape storage persists."""
    return {
        "status": summary.status,
        "requested_count": summary.request.requested_count,
        "accepted_count": summary.accepted_count,
        "examples_per_type": summary.request.examples_per_type,
        "max_attempts": summary.request.max_attempts,
        "error": summary.error,
        "attempts": [_trace_to_dict(trace) for trace in summary.traces],
    }


def _trace_to_dict(trace: HarnessQuestionTrace) -> dict:
    return {
        "requested_type": trace.requested_type,
        "resolved_type": trace.resolved_type,
        "attempt_number": trace.attempt_number,
        "used_tool_path": trace.used_tool_path,
        "accepted": trace.accepted,
        "json_repair_attempts": trace.json_repair_attempts,
        "verdict": trace.verification.verdict,
        "verifier_notes": trace.verification.notes,
        "guardrail_errors": list(trace.guardrail_errors),
        "tool_calls": [call.as_dict() for call in trace.tool_calls],
        "raw_output": trace.raw_model_output,
        "final_output": trace.final_output,
    }


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
            parts.append(_format_text_table(question))
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


def _format_text_table(question: Question) -> str:
    rows = _parse_text_table_rows(question.stimulus)
    if not rows:
        return question.stimulus

    if question.question_type == "Attention to Detail":
        width = max(len(row) for row in rows)
        return _markdown_table([""] * width, rows)

    header = rows[0]
    body = rows[1:]
    if body and all(len(row) == len(header) for row in body):
        return _markdown_table(header, body)

    width = max(len(row) for row in rows)
    return _markdown_table([""] * width, rows)


def _parse_text_table_rows(stimulus: str) -> list[list[str]]:
    return [
        [_escape_table_cell(cell.strip()) for cell in row.split("|")]
        for row in stimulus.split(";")
        if row.strip()
    ]


def _markdown_table(header: list[str], rows: list[list[str]]) -> str:
    width = len(header)
    lines = [
        _markdown_table_row(_pad_cells(header, width)),
        _markdown_table_row(["---"] * width),
    ]
    lines.extend(_markdown_table_row(_pad_cells(row, width)) for row in rows)
    return "\n".join(lines)


def _markdown_table_row(cells: list[str]) -> str:
    return f"| {' | '.join(cells)} |"


def _pad_cells(cells: list[str], width: int) -> list[str]:
    return [*cells[:width], *([""] * max(width - len(cells), 0))]


def _escape_table_cell(cell: str) -> str:
    return cell.replace("|", "\\|")


def _image_markdown(image_path: Path) -> str:
    return f"![Question image]({image_path})"
