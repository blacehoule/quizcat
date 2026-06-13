# QuizCat Web Front End — Plan

Goal: make QuizCat usable from a browser instead of (or in addition to) the terminal.

There are two viable approaches, in increasing order of effort. They aren't mutually exclusive — Path A is a fast way to get something live now, and Path B is the "real" web app if Path A's UX isn't enough.

## Path A — Serve the existing TUI in a browser (textual-serve)

Textual apps can be served as-is: the same Python process runs the app, and only rendering commands stream to the browser over a websocket. No UI code changes required.

**Steps**

1. Add the dependency: `uv add textual-serve`
2. Create a small `serve.py`:
   ```python
   from textual_serve.server import Server

   server = Server("uv run python main.py")
   server.serve()
   ```
3. Run `uv run python serve.py` — it prints a local URL (default `http://localhost:8000`) that renders the app in-browser via xterm-style terminal emulation.
4. Verify the things that are environment-sensitive in a browser context:
   - Image-stimulus questions (`image_rendering.py` picks a renderer based on terminal capabilities — browser terminal emulation may pick a different/lower-quality one)
   - Keyboard navigation for the `ListView` choice picker
   - Layout at typical browser window widths
5. For access beyond your machine: either expose port 8000 behind your own reverse proxy (nginx/Caddy + TLS), or use Textualize's hosted `textual-web` if you want a public URL without managing your own server.

**Pros**: ~30 minutes of work, zero changes to `models.py`/`storage.py`/`services.py`/`screens.py`. Good for "let me try this from my laptop browser" or sharing with a couple people on your network.

**Cons**: it's still visually a terminal app (monospace grid, TUI widgets) — not a typical responsive web UI. Each browser session spawns a subprocess running the full app + SQLite connection, so it doesn't scale to many concurrent users without more work.

## Path B — Real web app on top of the existing service layer

The codebase is already split cleanly: `models.py` (data), `storage.py` (SQLite), `services.py` (`QuizService` — the API the UI calls). None of that is Textual-specific, so it can be reused as the backend for an HTTP API. Only `screens.py`/`widgets.py`/`quizcat.tcss` get replaced.

**Phase 1 — API layer (FastAPI)**

Wrap `QuizService` in a small FastAPI app:

- `GET /tests` → `list_tests()`
- `GET /tests/{id}` → `get_test()`
- `POST /attempts` → `create_attempt()` (start a quiz)
- `POST /attempts/{id}/answers` → `evaluate_answer()` + `record_answer()`
- `POST /attempts/{id}/finish` → `finish_attempt()`
- `GET /attempts` → `list_finished_attempts()`
- `GET /images/{filename}` → serve files from `images/`

One open question: SQLite + multiple users. Fine for single-user/local use as-is; if multiple people use it concurrently, attempts need a session/user id added to the schema.

**Phase 2 — Frontend skeleton**

Pick a stack — plain HTML/JS + a CSS framework is enough given the app's small surface area (3 screens), or React/Vite if you want componentization. Pages mirror the existing screens:

- Dashboard (exam list, "Start Quiz", "View Stats")
- Quiz screen (timer, progress bar, question + choices, controls)
- Stats screen (finished attempts list)

**Phase 3 — Quiz flow**

- Re-implement the 15-minute countdown timer and progress meter in JS (the logic in `screens.py`'s `QuizScreen` is the reference — `_elapsed_seconds`, `_tick`, pause/resume)
- Render question content: `services.format_question_content()` already returns Markdown + an image path — render Markdown client-side (e.g. `markdown-it`, same library the Python side uses) and serve images via the `/images/` endpoint
- `text_table` stimuli currently render as Markdown tables — these render fine in any Markdown renderer, no extra work
- Submit flow: POST selected choice to `/attempts/{id}/answers`, advance question client-side

**Phase 4 — Persistence & stats**

- Wire "Start Quiz" → `POST /attempts`, each "Submit" → `POST /attempts/{id}/answers`, end-of-quiz → `POST /attempts/{id}/finish`
- Stats screen → `GET /attempts`, render the same fields as `StatsDashboardScreen._attempt_label`

**Phase 5 — Polish**

- Responsive layout for mobile
- Styling pass (the TUI's `quizcat.tcss` color/spacing choices can inform a theme)
- Deployment (containerize FastAPI + static frontend, or serve frontend from FastAPI's static files)

## Recommendation

Start with **Path A** today to get a working browser version with near-zero effort and confirm it's not "good enough" before investing in Path B. If the TUI-in-browser look/feel isn't what you want, Path B is a clean lift because the data/service layer is already UI-agnostic — the API layer (Phase 1) is the only new "backend" work; everything else is frontend.

## Open questions to resolve before Path B

- Single-user (current SQLite-per-process model is fine) vs multi-user (needs auth + per-user attempt tracking)?
- Hosting target (local-only, home network, or public internet)?
- Frontend stack preference (plain HTML/JS vs React)?
