"""Reusable widgets for QuizCat screens.

Each widget here is intentionally presentation-focused: it owns its layout
and DOM children, but it does not own quiz state. Callers pass content in
via the constructor (see `QAPanel`) and update display widgets through small
rendering methods. Behavioural state (paused, time remaining, current
question index) lives one level up, on whichever Screen hosts the widget.

That separation matters as the app grows. The same `QAPanel` can render any
question/answer pair, and the same `ControlPanel` works for both the live
quiz and a future review mode without forking.

Styling lives in `quizcat.tcss`, scoped by class name (e.g. `TimerBar`) or
id (e.g. `#question`). Control behaviour belongs on the screen, not here.
"""

from math import ceil, floor

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Label,
    ListItem,
    ListView,
    Markdown,
    ProgressBar,
    Static,
    Switch,
)


# ---------------------------------------------------------------------------
# Meter widgets
#
# Both meters use the same recipe: a horizontal row with a leading
# ProgressBar that stretches to fill, and a trailing Label for the
# human-readable value (e.g. "12:00" or "1 / 50"). The recipe is duplicated
# rather than abstracted because (a) there are only two, and (b) the timer
# and progress meter will diverge as they're wired up — different update
# cadences, different reactive sources, possibly different colours.
# ---------------------------------------------------------------------------


class TimerBar(Horizontal):
    """Top-of-screen pacing meter.

    The bar visualises percent of test time elapsed; the trailing label is
    where a `mm:ss` readout is written. The readout can show either time
    remaining or elapsed time; the bar always tracks elapsed time.

    The border around the row is coloured `$success` in CSS to reinforce
    that this meter is about *pacing* (green = good, you have time). Once
    the timer crosses a threshold (e.g. last two minutes) the colour could
    be swapped to `$warning` or `$error`.
    """

    def on_mount(self) -> None:
        # `border_title` is set after mount so Textual picks it up alongside
        # the `border: round` rule from the stylesheet. Doing this in
        # on_mount (rather than as a class attribute) is the version-safe
        # path — earlier Textual releases didn't honour class-level titles.
        self.border_title = "Time"

    def compose(self) -> ComposeResult:
        # show_eta and show_percentage are disabled because the trailing
        # Label is the canonical place for the numeric readout. Leaving
        # them on would double up the information and crowd the row.
        yield ProgressBar(
            total=100,
            show_eta=False,
            show_percentage=False,
            id="timer-progress",
        )
        yield Label("15:00", id="timer-value", classes="meter-value")

    def update_time(
        self,
        elapsed_seconds: float,
        total_seconds: int,
        *,
        show_elapsed: bool = False,
    ) -> None:
        """Render timer progress and the selected clock readout."""
        elapsed_seconds = min(max(elapsed_seconds, 0.0), total_seconds)
        progress = (elapsed_seconds / total_seconds) * 100 if total_seconds else 100
        display_seconds = (
            floor(elapsed_seconds)
            if show_elapsed
            else ceil(total_seconds - elapsed_seconds)
        )

        self.query_one("#timer-progress", ProgressBar).update(
            total=100,
            progress=progress,
        )
        self.query_one("#timer-value", Label).update(
            self._format_seconds(display_seconds)
        )

    @staticmethod
    def _format_seconds(seconds: int) -> str:
        minutes, seconds = divmod(max(seconds, 0), 60)
        return f"{minutes:02}:{seconds:02}"


class ProgressMeter(Horizontal):
    """Question-completion meter.

    Same shape as `TimerBar` but bound to a different signal: answered /
    total. With 50 questions in the default quiz, each answer advances the
    bar by 2% — matching the project layout notes.
    """

    def on_mount(self) -> None:
        self.border_title = "Progress"

    def compose(self) -> ComposeResult:
        yield ProgressBar(
            total=50,
            show_eta=False,
            show_percentage=False,
            id="question-progress",
        )
        yield Label("0 / 50", id="question-progress-value", classes="meter-value")

    def update_progress(self, answered: int, total: int) -> None:
        """Render answered-question progress."""
        answered = min(max(answered, 0), total)
        self.query_one("#question-progress", ProgressBar).update(
            total=total,
            progress=answered,
        )
        self.query_one("#question-progress-value", Label).update(
            f"{answered} / {total}"
        )


# ---------------------------------------------------------------------------
# Question / Answer panel
# ---------------------------------------------------------------------------


class QAPanel(Horizontal):
    """Question card on the left, answer choices on the right.

    The question pane is wrapped in a `VerticalScroll` so multi-paragraph
    stimuli (reading-comp passages, long word problems, attention-to-detail
    tables) can scroll inside their own pane without forcing the whole
    screen to resize. CCAT items have at most five short answer choices, so
    the choices column is kept intentionally narrow.

    Parameters
    ----------
    prompt_markdown:
        The full Markdown body for the question — typically prompt +
        stimulus joined into the template defined in `example_question.py`.
        Passed in by the screen rather than imported here so the widget
        stays reusable for any question source.
    choices:
        Mapping of choice label (``"A".."E"``) to choice text. Iteration
        order is preserved as-is, because the CCAT bank ships choices in
        their canonical display order and reordering them would invalidate
        the answer key.
    """

    def __init__(
        self,
        prompt_markdown: str,
        choices: dict[str, str],
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        # Stash the inputs on the instance; `compose` is the first place
        # they're actually consumed (after `__init__` returns, but before
        # `on_mount`).
        self._prompt_markdown = prompt_markdown
        self._choices = choices

    def compose(self) -> ComposeResult:
        # Left pane: the question card. Wrapping the Markdown widget in a
        # VerticalScroll is what makes long content scroll instead of
        # squishing the rest of the layout.
        question_pane = VerticalScroll(
            Markdown(self._prompt_markdown),
            id="question",
        )
        question_pane.border_title = "Question"
        yield question_pane

        # Right pane: the answer choices. A ListView gives us keyboard
        # navigation and a built-in selection event for free, which the
        # screen subscribes to when Submit is pressed.
        choices_pane = ListView(
            *[
                ListItem(Label(f"{label}. {text}"))
                for label, text in self._choices.items()
            ],
            id="choices",
        )
        choices_pane.border_title = "Choices"
        yield choices_pane


class PausedPanel(Vertical):
    """Temporary replacement for question content while the quiz is paused."""

    def compose(self) -> ComposeResult:
        yield Static("Paused ||", id="paused-title")


class SummaryPanel(Vertical):
    """End-of-quiz score summary.

    Scoring is placeholder-only until real answer checking is wired in.
    The screen still passes real completion context such as questions
    submitted and time used.
    """

    def compose(self) -> ComposeResult:
        yield Static("Quiz Complete", id="summary-title")
        yield Static("Score: -- / 50", id="summary-score")
        yield Static("Submitted: 0 / 50", id="summary-submitted")
        yield Static("Time Used: 00:00", id="summary-time")
        yield Static("Accuracy: --%", id="summary-accuracy")

    def update_summary(
        self,
        *,
        answered: int,
        total_questions: int,
        elapsed_seconds: float,
        ended_by_time: bool,
    ) -> None:
        """Render the available end-of-quiz summary values."""
        title = "Time Expired" if ended_by_time else "Quiz Complete"
        self.query_one("#summary-title", Static).update(title)
        self.query_one("#summary-score", Static).update(
            f"Score: -- / {total_questions}"
        )
        self.query_one("#summary-submitted", Static).update(
            f"Submitted: {answered} / {total_questions}"
        )
        self.query_one("#summary-time", Static).update(
            f"Time Used: {self._format_seconds(elapsed_seconds)}"
        )
        self.query_one("#summary-accuracy", Static).update("Accuracy: --%")

    @staticmethod
    def _format_seconds(seconds: float) -> str:
        minutes, seconds = divmod(int(seconds), 60)
        return f"{minutes:02}:{seconds:02}"


# ---------------------------------------------------------------------------
# Control panel
# ---------------------------------------------------------------------------


class ControlPanel(Horizontal):
    """Bottom action bar.

    Buttons, in DOM order:

    * **Pause**  — freeze the timer and disable Submit.
    * **Resume** — mounted hidden (``display: none`` in CSS). When the quiz
      enters the paused state, CSS will flip Pause hidden and Resume
      visible so the same panel slot toggles labels in place without the
      neighbouring buttons jumping around.
    * **Abort**  — leave the current quiz and return to the dashboard.
    * **Elapsed switch** — toggles the timer readout between remaining time
      and elapsed time. The progress bar always tracks elapsed time.
    * **Submit** — count the current example question as answered. Real
      answer validation will replace that placeholder behaviour once the
      CSV bank is wired in.
    * **Dashboard** — mounted hidden until the quiz ends, then replaces
      Submit as the only visible action.

    The DOM order is left → right, but Submit is docked to the right edge
    of the panel in the stylesheet (``dock: right``). That keeps Submit
    anchored to the trailing edge whether Pause or Resume is currently
    showing, so the visual hierarchy is stable across state changes.
    """

    def compose(self) -> ComposeResult:
        # State-management buttons cluster on the leading edge. Pause comes
        # first because it's the most frequent action during a real test;
        # Abort is the bail-out and sits beside it.
        yield Button("Pause", id="pause", variant="warning")
        yield Button("Resume", id="resume", variant="success")
        yield Button("Abort", id="abort", variant="error")
        yield Horizontal(
            Label("Elapsed"),
            Switch(id="timer-mode"),
            id="timer-mode-control",
        )

        # Submit is the primary action of the screen, so it gets the
        # high-contrast `success` variant and floats to the trailing edge.
        yield Button("Submit", id="submit", variant="success")
        yield Button("Dashboard", id="return-dashboard", variant="primary")
