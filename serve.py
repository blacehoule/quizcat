"""Serve QuizCat in a browser via textual-serve.

Run with::

    uv run python serve.py

Then open the printed URL (default http://localhost:8000) in a browser.
"""

from textual_serve.server import Server

server = Server("uv run python main.py")

if __name__ == "__main__":
    server.serve()
