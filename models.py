"""Domain models for QuizCat.

These dataclasses are the boundary between the Textual UI and persistence.
They deliberately model quiz data in application terms instead of mirroring
the seed CSV column-for-column.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Choice:
    """One answer choice in display order."""

    label: str
    text: str
    position: int


@dataclass(frozen=True)
class Question:
    """A multiple-choice question loaded from the application store."""

    id: int
    external_id: str | None
    origin: str
    source_exam: str | None
    source_file: str | None
    source_category: str | None
    source_question_number: str | None
    category: str
    question_type: str
    prompt: str
    stimulus: str
    stimulus_type: str
    correct_choice_label: str
    correct_choice_text: str
    explanation: str
    choices: tuple[Choice, ...]

    def choice_for_label(self, label: str) -> Choice | None:
        """Return the choice with the given label, case-insensitively."""
        normalized = label.upper()
        for choice in self.choices:
            if choice.label.upper() == normalized:
                return choice
        return None


@dataclass(frozen=True)
class TestSummary:
    """Lightweight test metadata for dashboard lists."""

    id: int
    title: str
    kind: str
    source_exam: str | None
    question_count: int
    time_limit_seconds: int


@dataclass(frozen=True)
class TestDefinition:
    """A playable test with ordered questions."""

    id: int
    title: str
    kind: str
    source_exam: str | None
    question_count: int
    time_limit_seconds: int
    questions: tuple[Question, ...]


@dataclass(frozen=True)
class QuizAttempt:
    """Persisted quiz attempt metadata."""

    id: int
    test_id: int
    status: str
    started_at: str
    finished_at: str | None
    elapsed_seconds: float
    answered_count: int
    correct_count: int
    total_questions: int


@dataclass(frozen=True)
class AttemptAnswer:
    """One submitted answer for a quiz attempt."""

    id: int
    attempt_id: int
    question_id: int
    question_position: int
    selected_choice_label: str
    selected_choice_text: str
    is_correct: bool
    elapsed_seconds: float


@dataclass(frozen=True)
class QuizResult:
    """Final scoring summary for an attempt."""

    attempt_id: int
    status: str
    elapsed_seconds: float
    answered_count: int
    correct_count: int
    total_questions: int

    @property
    def accuracy_percent(self) -> float:
        """Correct answers divided by submitted answers."""
        if self.answered_count == 0:
            return 0.0
        return (self.correct_count / self.answered_count) * 100
