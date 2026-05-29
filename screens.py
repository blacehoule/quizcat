"""Screen-level layout for QuizCat.

A `Screen` is Textual's analogue of a "page": it owns the full viewport and
the high-level state that goes with it (which question we're on, time
remaining, whether the test is paused). Widgets composed inside a screen
should not reach back into that state directly; they receive data through
their constructors and expose events, and the screen mediates between them.

For now the only screen is `QuizScreen`. A future menu screen and post-quiz
results screen will sit alongside it in this module.
"""

from time import monotonic

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, ListItem, ListView, Switch

from example_question import EXAMPLE_ANSWERS, EXAMPLE_QUESTION
from widgets import (
    ControlPanel,
    PausedPanel,
    ProgressMeter,
    QAPanel,
    SummaryPanel,
    TimerBar,
)

EXAM_OPTIONS = tuple(f"Sample Exam {exam_number}" for exam_number in range(1, 9))


class DashboardScreen(Screen):
    """Start screen for choosing which sample exam to practice."""

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="dashboard-body"):
            yield Label("Choose a Sample Exam", id="dashboard-title")
            yield ListView(
                *[
                    ListItem(Label(exam_name), id=f"exam-{index + 1}")
                    for index, exam_name in enumerate(EXAM_OPTIONS)
                ],
                id="exam-list",
            )
            yield Button("Start Quiz", id="start-quiz", variant="success")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#exam-list", ListView).border_title = "Available Exams"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start-quiz":
            self._start_selected_quiz()

    def _start_selected_quiz(self) -> None:
        exam_list = self.query_one("#exam-list", ListView)
        selected_index = exam_list.index or 0
        self.app.push_screen(
            QuizScreen(
                selected_exam=EXAM_OPTIONS[selected_index],
            )
        )


class QuizScreen(Screen):
    """The active-test screen.

    Top-to-bottom layout (rendered by the ``Vertical(id="quiz-body")``
    container)::

        ┌─────────── Header ────────────┐
        │ ┌ Time ──[████░░░░░] 12:00 ─┐ │   ← TimerBar
        │ └────────────────────────────┘ │
        │ ┌ Progress [██░░░░░░] 1 / 50 ┐ │   ← ProgressMeter
        │ └────────────────────────────┘ │
        │ ┌ Question ─────┐ ┌ Choices ─┐ │
        │ │ prompt        │ │ A. ...   │ │   ← QAPanel
        │ │ stimulus      │ │ B. ...   │ │
        │ └───────────────┘ └──────────┘ │
        │ [Pause][Abort][Elapsed][Submit]│   ← ControlPanel
        └─────────── Footer ────────────┘

    The screen owns runtime quiz state: the 15-minute timer, pause/resume
    state, timer display mode, answered-question count, end state, and
    which content panel is visible.
    """

    TEST_SECONDS = 15 * 60
    TOTAL_QUESTIONS = 50

    def __init__(self, *, selected_exam: str) -> None:
        super().__init__()
        self.selected_exam = selected_exam
        self._answered_questions = 0
        self._elapsed_before_pause = 0.0
        self._ended = False
        self._paused = False
        self._show_elapsed = False
        self._started_at: float | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        # `Vertical` is the spine of the screen. Putting every child in a
        # single container (rather than yielding them straight to the
        # screen) makes them easy to address as a group from CSS via
        # `#quiz-body` and gives us a clean place to add screen-level
        # padding.
        with Vertical(id="quiz-body"):
            yield TimerBar(id="timer")
            yield ProgressMeter(id="progress")
            # The example question is imported at the screen layer (rather
            # than inside QAPanel) so QAPanel itself stays reusable for any
            # question source the app eventually loads from the CSV bank.
            yield QAPanel(EXAMPLE_QUESTION, EXAMPLE_ANSWERS, id="qa")
            yield PausedPanel(id="paused-panel")
            yield SummaryPanel(id="summary-panel")
            yield ControlPanel(id="controls")
        yield Footer()

    def on_mount(self) -> None:
        """Start the quiz timer after the screen is mounted."""
        self._started_at = monotonic()
        self.set_interval(0.25, self._tick)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle control-panel button presses."""
        match event.button.id:
            case "pause":
                self._pause_quiz()
            case "resume":
                self._resume_quiz()
            case "abort":
                self._return_to_dashboard()
            case "submit":
                self._submit_answer()
            case "return-dashboard":
                self._return_to_dashboard()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Switch timer readout between remaining and elapsed time."""
        if event.switch.id == "timer-mode":
            self._show_elapsed = event.value
            self._render_timer()
            event.stop()

    def _tick(self) -> None:
        if self._paused or self._ended:
            return

        self._render_timer()
        if self._elapsed_seconds() >= self.TEST_SECONDS:
            self._end_quiz(ended_by_time=True)

    def _pause_quiz(self) -> None:
        if self._paused or self._ended:
            return

        self._elapsed_before_pause = self._elapsed_seconds()
        self._started_at = None
        self._paused = True
        self._render_timer()
        self._sync_quiz_state()

    def _resume_quiz(self) -> None:
        if not self._paused or self._ended:
            return

        self._started_at = monotonic()
        self._paused = False
        self._render_timer()
        self._sync_quiz_state()

    def _submit_answer(self) -> None:
        if self._paused or self._ended:
            return

        self._answered_questions = min(
            self._answered_questions + 1,
            self.TOTAL_QUESTIONS,
        )
        self._render_progress()
        if self._answered_questions >= self.TOTAL_QUESTIONS:
            self._end_quiz(ended_by_time=False)

    def _elapsed_seconds(self) -> float:
        if self._started_at is None:
            return self._elapsed_before_pause
        return min(
            self._elapsed_before_pause + (monotonic() - self._started_at),
            self.TEST_SECONDS,
        )

    def _render_timer(self) -> None:
        self.query_one("#timer", TimerBar).update_time(
            self._elapsed_seconds(),
            self.TEST_SECONDS,
            show_elapsed=self._show_elapsed,
        )

    def _render_progress(self) -> None:
        self.query_one("#progress", ProgressMeter).update_progress(
            self._answered_questions,
            self.TOTAL_QUESTIONS,
        )

    def _end_quiz(self, *, ended_by_time: bool) -> None:
        if self._ended:
            return

        self._elapsed_before_pause = self._elapsed_seconds()
        self._started_at = None
        self._paused = False
        self._ended = True
        self._render_timer()
        self.query_one("#summary-panel", SummaryPanel).update_summary(
            answered=self._answered_questions,
            total_questions=self.TOTAL_QUESTIONS,
            elapsed_seconds=self._elapsed_before_pause,
            ended_by_time=ended_by_time,
        )
        self._sync_quiz_state()

    def _sync_quiz_state(self) -> None:
        quiz_body = self.query_one("#quiz-body", Vertical)
        quiz_body.set_class(self._paused, "paused")
        quiz_body.set_class(self._ended, "ended")
        controls = self.query_one("#controls", ControlPanel)
        controls.set_class(self._paused, "paused")
        controls.set_class(self._ended, "ended")
        self.query_one("#pause", Button).disabled = self._ended
        self.query_one("#resume", Button).disabled = self._ended
        self.query_one("#submit", Button).disabled = self._paused or self._ended

    def _return_to_dashboard(self) -> None:
        self.app.pop_screen()
