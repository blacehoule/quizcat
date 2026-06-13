"""Serve QuizCat in a browser via textual-serve.

Run with::

    python serve.py

Locally, open http://localhost:8000. On Railway, the server binds to the
platform-provided PORT on all network interfaces.
"""

import os
import sys

from textual_serve.server import Server

host = os.environ.get("HOST", "0.0.0.0")
port = int(os.environ.get("PORT", "8000"))
railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
public_url = os.environ.get("PUBLIC_URL")

if public_url is None:
    public_url = (
        f"https://{railway_domain}"
        if railway_domain
        else f"http://localhost:{port}"
    )

server = Server(
    f'"{sys.executable}" main.py',
    host=host,
    port=port,
    title="QuizCat",
    public_url=public_url,
)

if __name__ == "__main__":
    server.serve()
