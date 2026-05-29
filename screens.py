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
from textual.widgets import Button, Footer, Header, Switch

from example_question import EXAMPLE_ANSWERS, EXAMPLE_QUESTION
from widgets import ControlPanel, PausedPanel, ProgressMeter, QAPanel, TimerBar


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
    state, timer display mode, answered-question count, and which content
    panel is visible.
    """

    TEST_SECONDS = 15 * 60
    TOTAL_QUESTIONS = 50

    def __init__(self) -> None:
        super().__init__()
        self._answered_questions = 0
        self._elapsed_before_pause = 0.0
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
                self.app.exit()
            case "submit":
                self._submit_answer()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Switch timer readout between remaining and elapsed time."""
        if event.switch.id == "timer-mode":
            self._show_elapsed = event.value
            self._render_timer()
            event.stop()

    def _tick(self) -> None:
        if not self._paused:
            self._render_timer()

    def _pause_quiz(self) -> None:
        if self._paused:
            return

        self._elapsed_before_pause = self._elapsed_seconds()
        self._started_at = None
        self._paused = True
        self._render_timer()
        self._sync_pause_controls()

    def _resume_quiz(self) -> None:
        if not self._paused:
            return

        self._started_at = monotonic()
        self._paused = False
        self._render_timer()
        self._sync_pause_controls()

    def _submit_answer(self) -> None:
        if self._paused:
            return

        self._answered_questions = min(
            self._answered_questions + 1,
            self.TOTAL_QUESTIONS,
        )
        self._render_progress()

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

    def _sync_pause_controls(self) -> None:
        self.query_one("#quiz-body", Vertical).set_class(self._paused, "paused")
        self.query_one("#controls", ControlPanel).set_class(self._paused, "paused")
        self.query_one("#submit", Button).disabled = self._paused
