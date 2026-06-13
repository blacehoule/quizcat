"""Screen-level layout for QuizCat.

A `Screen` is Textual's analogue of a "page": it owns the full viewport and
the high-level state that goes with it (which question we're on, time
remaining, whether the test is paused). Widgets composed inside a screen
should not reach back into that state directly; they receive data through
their constructors and expose events, and the screen mediates between them.

The screen classes stay focused on UI state and delegate persistence,
scoring, and question loading to `QuizService`.
"""

from time import monotonic

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    Switch,
)
from textual.worker import Worker, WorkerState

from harness import create_chat_client
from models import (
    AttemptSummary,
    Question,
    QuizResult,
    SubmittedAnswer,
    TestDefinition,
    TestSummary,
)
from services import GeneratedTestResult, QuizService, create_quiz_service
from widgets import (
    ControlPanel,
    PausedPanel,
    ProgressMeter,
    QAPanel,
    SummaryPanel,
    TimerBar,
)


class DashboardScreen(Screen):
    """Start screen for choosing which sample exam to practice."""

    GENERATION_GROUP = "generate-test"

    def __init__(self, *, quiz_service: QuizService) -> None:
        super().__init__()
        self._quiz_service = quiz_service
        self._tests: list[TestSummary] = self._quiz_service.list_tests()
        self._generating = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="dashboard-body"):
            yield Label("Choose a Practice Test", id="dashboard-title")
            yield ListView(
                *self._exam_items(),
                initial_index=0 if self._tests else None,
                id="exam-list",
            )
            yield Label("", id="dashboard-status")
            with Horizontal(id="dashboard-actions"):
                yield Button("View Stats", id="view-stats", variant="primary")
                yield Button("Generate Test", id="generate-test", variant="warning")
                yield Button("Start Quiz", id="start-quiz", variant="success")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#exam-list", ListView).border_title = "Available Exams"
        self.query_one("#start-quiz", Button).disabled = not self._tests

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start-quiz":
            self._start_selected_quiz()
        elif event.button.id == "view-stats":
            self.app.push_screen(StatsDashboardScreen(quiz_service=self._quiz_service))
        elif event.button.id == "generate-test":
            self._start_generation()

    def _start_selected_quiz(self) -> None:
        if not self._tests:
            return

        exam_list = self.query_one("#exam-list", ListView)
        selected_index = exam_list.index or 0
        self._start_quiz_for_test(self._tests[selected_index].id)

    def _start_quiz_for_test(self, test_id: int) -> None:
        self.app.push_screen(
            QuizScreen(
                quiz_service=self._quiz_service,
                test=self._quiz_service.get_test(test_id),
            )
        )

    def _start_generation(self) -> None:
        """Kick off background test generation, guarding against re-entry."""
        if self._generating:
            return
        self._generating = True
        self.query_one("#generate-test", Button).disabled = True
        self._set_status("Generating a new test… this can take up to a minute.")
        self._generate_test_worker()

    @work(thread=True, exclusive=True, group=GENERATION_GROUP)
    def _generate_test_worker(self) -> GeneratedTestResult:
        """Run the (blocking) harness off the UI thread.

        SQLite connections are single-thread, so the worker opens its own
        connection to the same database file rather than sharing the UI
        thread's. Once it commits, the UI thread's connection sees the new
        rows. Returning a value or raising drives
        ``on_worker_state_changed``; the progress callback marshals live
        status back onto the UI thread.
        """
        client = create_chat_client()

        def on_question(event) -> None:
            self.app.call_from_thread(
                self._set_status,
                f"Generating… {event.position}/{event.requested_count} "
                f"({event.accepted_count} accepted so far)",
            )

        worker_service = create_quiz_service(
            db_path=self._quiz_service.db_path,
            seed_csv_path=None,
            image_asset_dir=self._quiz_service.image_asset_dir,
        )
        try:
            return worker_service.generate_test(client=client, on_question=on_question)
        finally:
            worker_service.close()

    async def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Finish the generation flow once the worker settles."""
        if event.worker.group != self.GENERATION_GROUP:
            return
        if event.state not in (WorkerState.SUCCESS, WorkerState.ERROR):
            return

        self._generating = False
        self.query_one("#generate-test", Button).disabled = False

        if event.state == WorkerState.ERROR:
            self._set_status("")
            self.app.notify(
                f"Test generation failed: {event.worker.error}", severity="error"
            )
            return

        result: GeneratedTestResult = event.worker.result
        if result.succeeded:
            await self._reload_tests(select_test_id=result.test_id)
            new_test = next(
                (test for test in self._tests if test.id == result.test_id), None
            )
            title = new_test.title if new_test else "New test"
            self._set_status(f"Added {title} ({result.summary.accepted_count} questions).")
            self.app.notify(f"{title} is ready to play.")
        else:
            self._set_status("Generation produced no valid questions.")
            self.app.notify(
                "Generation failed: no questions passed the guardrails.",
                severity="error",
            )

    def _set_status(self, message: str) -> None:
        self.query_one("#dashboard-status", Label).update(message)

    async def _reload_tests(self, *, select_test_id: int | None = None) -> None:
        self._tests = self._quiz_service.list_tests()
        exam_list = self.query_one("#exam-list", ListView)
        await exam_list.clear()
        await exam_list.extend(self._exam_items())
        if self._tests:
            index = 0
            if select_test_id is not None:
                index = next(
                    (
                        position
                        for position, test in enumerate(self._tests)
                        if test.id == select_test_id
                    ),
                    0,
                )
            exam_list.index = index
        self.query_one("#start-quiz", Button).disabled = not self._tests

    def _exam_items(self) -> list[ListItem]:
        return [
            ListItem(Label(self._test_label(test)), id=f"test-{test.id}")
            for test in self._tests
        ]

    @staticmethod
    def _test_label(test: TestSummary) -> str:
        minutes = test.time_limit_seconds // 60
        return f"{test.title} - {test.question_count} questions / {minutes} min"


class StatsDashboardScreen(Screen):
    """Screen for viewing historical finished-attempt summaries."""

    def __init__(self, *, quiz_service: QuizService) -> None:
        super().__init__()
        self._quiz_service = quiz_service
        self._attempts: list[AttemptSummary] = (
            self._quiz_service.list_finished_attempts()
        )

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="stats-body"):
            yield Label("Attempt Results", id="stats-title")
            yield ListView(
                *self._attempt_items(),
                initial_index=0 if self._attempts else None,
                id="attempt-list",
            )
            yield Button("View Tests", id="view-tests", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#attempt-list", ListView).border_title = "Finished Attempts"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "view-tests":
            self.app.pop_screen()

    def _attempt_items(self) -> list[ListItem]:
        if not self._attempts:
            return [ListItem(Label("No finished attempts yet"), id="stats-empty")]

        return [
            ListItem(Label(self._attempt_label(attempt)))
            for attempt in self._attempts
        ]

    @classmethod
    def _attempt_label(cls, attempt: AttemptSummary) -> str:
        return (
            f"Test ID: {attempt.test_id} - {attempt.test_title} | "
            f"Score: {attempt.correct_count} / {attempt.total_questions} | "
            f"Time: {cls._format_seconds(attempt.elapsed_seconds)}"
        )

    @staticmethod
    def _format_seconds(seconds: float) -> str:
        minutes, seconds = divmod(int(seconds), 60)
        return f"{minutes:02}:{seconds:02}"


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

    def __init__(self, *, quiz_service: QuizService, test: TestDefinition) -> None:
        if not test.questions:
            raise ValueError("A quiz test must include at least one question")
        super().__init__()
        self._quiz_service = quiz_service
        self.test = test
        self._result: QuizResult | None = None
        self._submitted_answers: list[SubmittedAnswer] = []
        self._answered_questions = 0
        self._correct_answers = 0
        self._current_index = 0
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
            # The screen formats question data before passing it into
            # QAPanel, so the widget stays reusable for any question source.
            first_question = self._current_question()
            yield QAPanel(
                self._quiz_service.question_content(first_question),
                self._choices_for_question(first_question),
                id="qa",
            )
            yield PausedPanel(id="paused-panel")
            yield SummaryPanel(id="summary-panel")
            yield ControlPanel(id="controls")
        yield Footer()

    def on_mount(self) -> None:
        """Start the quiz timer after the screen is mounted."""
        self._started_at = monotonic()
        self._render_timer()
        self._render_progress()
        self._sync_quiz_state()
        self.set_interval(0.25, self._tick)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle control-panel button presses."""
        match event.button.id:
            case "pause":
                self._pause_quiz()
            case "resume":
                self._resume_quiz()
            case "abort":
                self._return_to_dashboard()
            case "submit":
                await self._submit_answer()
            case "return-dashboard":
                self._return_to_dashboard()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Switch timer readout between remaining and elapsed time."""
        if event.switch.id == "timer-mode":
            self._show_elapsed = event.value
            self._render_timer()
            event.stop()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Enable Submit once the user has highlighted an answer choice."""
        if event.list_view.id == "choices":
            self._sync_quiz_state()
            event.stop()

    def _tick(self) -> None:
        if self._paused or self._ended:
            return

        self._render_timer()
        if self._elapsed_seconds() >= self.time_limit_seconds:
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

    async def _submit_answer(self) -> None:
        if self._paused or self._ended:
            return

        selected_choice_label = self.query_one(
            "#qa",
            QAPanel,
        ).selected_choice_label()
        if selected_choice_label is None:
            self._sync_quiz_state()
            return

        answer = self._quiz_service.evaluate_answer(
            question=self._current_question(),
            question_position=self._current_index + 1,
            selected_choice_label=selected_choice_label,
            elapsed_seconds=self._elapsed_seconds(),
        )
        self._submitted_answers.append(answer)
        self._answered_questions += 1
        if answer.is_correct:
            self._correct_answers += 1
        self._current_index += 1

        self._render_progress()
        if self._current_index >= self.total_questions:
            self._end_quiz(ended_by_time=False)
            return

        await self._render_current_question()
        self._sync_quiz_state()

    def _elapsed_seconds(self) -> float:
        if self._started_at is None:
            return self._elapsed_before_pause
        return min(
            self._elapsed_before_pause + (monotonic() - self._started_at),
            self.time_limit_seconds,
        )

    def _render_timer(self) -> None:
        self.query_one("#timer", TimerBar).update_time(
            self._elapsed_seconds(),
            self.time_limit_seconds,
            show_elapsed=self._show_elapsed,
        )

    def _render_progress(self) -> None:
        self.query_one("#progress", ProgressMeter).update_progress(
            self._answered_questions,
            self.total_questions,
        )

    async def _render_current_question(self) -> None:
        question = self._current_question()
        await self.query_one("#qa", QAPanel).update_question(
            self._quiz_service.question_content(question),
            self._choices_for_question(question),
        )

    def _end_quiz(self, *, ended_by_time: bool) -> None:
        if self._ended:
            return

        self._elapsed_before_pause = self._elapsed_seconds()
        self._started_at = None
        self._paused = False
        self._ended = True
        self._result = self._quiz_service.record_finished_attempt(
            test_id=self.test.id,
            status="timed_out" if ended_by_time else "completed",
            elapsed_seconds=self._elapsed_before_pause,
            total_questions=self.total_questions,
            answers=tuple(self._submitted_answers),
        )
        self._answered_questions = self._result.answered_count
        self._correct_answers = self._result.correct_count
        self._render_timer()
        self._render_progress()
        self.query_one("#summary-panel", SummaryPanel).update_summary(
            answered=self._answered_questions,
            correct=self._correct_answers,
            total_questions=self.total_questions,
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
        has_selection = (
            self.query_one("#qa", QAPanel).selected_choice_label() is not None
        )
        self.query_one("#submit", Button).disabled = (
            self._paused or self._ended or not has_selection
        )

    def _return_to_dashboard(self) -> None:
        self.app.pop_screen()

    def _current_question(self) -> Question:
        return self.test.questions[self._current_index]

    @property
    def total_questions(self) -> int:
        return len(self.test.questions)

    @property
    def time_limit_seconds(self) -> int:
        return self.test.time_limit_seconds

    @staticmethod
    def _choices_for_question(question: Question) -> dict[str, str]:
        return {choice.label: choice.text for choice in question.choices}
