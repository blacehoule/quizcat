# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

QuizCat is a Textual-based terminal UI for timed, CCAT-style multiple-choice practice tests. The app is early-stage: layout is being scaffolded against a single hard-coded `example_question.py`, and the question bank in `ccat_full_question_bank_prompt_stimulus.csv` has not yet been wired into the app.

## Commands

Dependencies are managed by uv (`uv.lock` is committed) and the project requires Python 3.14+.

- Install/sync deps: `uv sync`
- Run the app: `uv run python main.py` (or `python main.py` inside the activated `.venv`)
- Run the Textual stopwatch tutorial reference app: `uv run python stopwatch_tutorial.py`

There is no test suite, linter, or formatter configured yet — do not invent commands for them.

When iterating on the TUI, prefer `textual run --dev main.py` so the dev console can show logs/CSS errors; otherwise the screen swallows tracebacks.

## Architecture

The Textual app is a thin three-layer composition:

- `QuizCat` (App) in `main.py` — owns the title/subtitle, the `d` dark-mode binding, and pushes `DashboardScreen` on ready. CSS is loaded from `quizcat.tcss`.
- `DashboardScreen` (Screen) — lets the user choose from 8 placeholder sample exams and start a quiz. It pushes `QuizScreen` with the selected exam label.
- `QuizScreen` (Screen) — vertical stack of: `TimerBar`, `ProgressMeter`, one content panel (`QAPanel`, `PausedPanel`, or `SummaryPanel`), and `ControlPanel`. It owns the 15-minute timer, pause/resume state, timer display mode, answered-question count, end state, selected exam label, and which content panel is visible.
- `QAPanel` / `PausedPanel` / `SummaryPanel` / `ControlPanel` — `QAPanel` renders the question as `Markdown` in a scrollable pane on the left and choices as a `ListView` on the right. `PausedPanel` replaces it while paused. `SummaryPanel` replaces it when time expires or all 50 questions are submitted. `ControlPanel` holds `Pause` / `Resume` / `Abort` / timer mode `Switch` / `Submit` controls; `Resume` is hidden via CSS (`display: none`) and swaps in for `Pause` when the quiz is paused.

Current quiz behavior:
- The timer runs for 15 minutes. Its progress bar tracks elapsed time; the switch toggles the label between remaining time and elapsed time.
- Each `Submit` press advances the question progress meter by one of 50 questions, i.e. 2%.
- Pause freezes the timer, swaps `Pause` for `Resume`, hides the question and answers behind the pause screen, and disables Submit.
- The quiz ends when time expires or when the 50th question is submitted. The summary card uses placeholder scoring until real answer validation exists.
- Abort returns to the dashboard. After a quiz ends, the control panel hides the other controls and shows a dashboard-return button.
- The layout still uses `EXAMPLE_QUESTION`; real answer validation is not implemented yet.

`stopwatch_tutorial.py` / `stopwatch.tcss` are an unmodified copy of the upstream Textual stopwatch tutorial, kept as a reference for timer patterns (reactive attributes, `set_interval`, start/stop/reset). Do not import from it — copy patterns as needed. `assets.py` holds ASCII banners (`banner`, `preamble`, `wink_eye_cat`, `open_eye_cat`) for menu/end screens that don't exist yet.

## Question bank (`ccat_full_question_bank_prompt_stimulus.csv`)

400 rows seeded from 8 BoostPrep exams (50 each). When writing importers or any code that touches this CSV, follow the rules from `README.md` — they are load-bearing and not obvious from the schema:

- `prompt` (reusable instruction) and `stimulus` (per-question content) are intentionally separate — do not concatenate them.
- `stimulus_type` ∈ {`text`, `text_table`, `image`}. For `image`, `stimulus` (or `image_filename`) holds the filename verbatim — preserve it exactly and do not drop image-based questions.
- Answer choices are `choice_a`..`choice_e`; not every question has all five. Preserve both `correct_choice_label` and `correct_choice_text` because choice ordering matters at render time.
- Treat `category`, `question_type`, `stimulus_type` as controlled vocabularies. The README enumerates the allowed values; small variants were intentionally rolled up (e.g. all numeric sequences → `Number Series`) — do not re-split them.
- Retain `source_exam` / `source_file` so a question can be traced back to its origin exam.
- Use a real CSV parser (`csv` module or pandas) — explanations contain commas, quotes, and newlines.
- Validate on import: every row needs a prompt or stimulus, at least one choice, a correct answer, a category, and a question type.
