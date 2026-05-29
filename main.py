"""QuizCat — a Textual TUI for CCAT-style practice quizzes.

Module map
----------
``main.py``      App subclass and entry point (this file). Owns global
                 concerns only: title, theme, root key bindings, initial
                 screen.
``screens.py``   ``Screen`` subclasses. A screen is one "page" of the app
                 and is responsible for high-level state.
``widgets.py``   Reusable composable widgets (Q/A panel, control bar, the
                 labeled meters). Pure presentation — no quiz state.
``quizcat.tcss`` Stylesheet. Rules are organised top-down to follow the
                 reader's eye down the quiz screen.

Run from a uv-managed checkout with::

    uv run python main.py
"""

from textual.app import App

from screens import QuizScreen


class QuizCat(App):
    """Top-level application.

    Stays intentionally small: anything that isn't global lives on the
    screen instead. As new screens are added (start menu, post-quiz
    results, pause overlay) they just become additional ``push_screen``
    calls — no churn here.
    """

    TITLE = "QuizCat"
    SUB_TITLE = "Cognitive Quizzes in the Command Line"
    CSS_PATH = "quizcat.tcss"

    # Bindings declared on the App apply on every screen. Screen-specific
    # bindings live on the Screen subclass and are merged in additively by
    # Textual, so per-screen behaviour can extend rather than replace this
    # list.
    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
    ]

    def on_ready(self) -> None:
        """Push the quiz screen once the app's first layout pass is done.

        Using ``on_ready`` rather than ``on_mount`` ensures the main window
        is fully sized before we mount the quiz screen — that avoids a
        one-frame flicker where the unframed default screen briefly shows
        through.
        """
        self.push_screen(QuizScreen())

    def action_toggle_dark(self) -> None:
        """Flip between Textual's bundled light and dark themes.

        Bound to ``d`` via ``BINDINGS`` above. The Footer picks the binding
        up automatically and renders the hint.
        """
        self.theme = (
            "textual-dark" if self.theme == "textual-light" else "textual-light"
        )


if __name__ == "__main__":
    QuizCat().run()
