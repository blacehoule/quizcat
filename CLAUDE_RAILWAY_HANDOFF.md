# QuizCat Textual Railway Deployment Handoff

## Goal

Deploy the existing Textual terminal application as a browser-accessible service
on Railway using `textual-serve`.

## Live Deployment

- Railway project: `quizcat-textual`
- Public URL: https://quizcat-textual-production.up.railway.app
- Railway dashboard:
  https://railway.com/project/ffa41b8d-4009-411b-ad20-0130c9c2328a/service/8d906dbe-9dcd-4f1c-939b-1ee7df612d0c
- Deployment result: `SUCCESS`
- Public endpoint verification: HTTP `200`

Railway currently assigns port `8080` through its `PORT` environment variable.
Local development continues to default to `http://localhost:8000`.

## Changes Made

### `serve.py`

Updated the Textual browser-server entrypoint to:

- Read `HOST`, defaulting to `0.0.0.0`
- Read Railway's injected `PORT`, defaulting to `8000`
- Launch `main.py` with the active Python interpreter
- Set the browser title to `QuizCat`

Current relevant behavior:

```python
host = os.environ.get("HOST", "0.0.0.0")
port = int(os.environ.get("PORT", "8000"))

server = Server(
    f'"{sys.executable}" main.py',
    host=host,
    port=port,
    title="QuizCat",
)
```

### `railway.toml`

Added Railway configuration-as-code:

```toml
[build]
builder = "RAILPACK"

[deploy]
startCommand = "python serve.py"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

### `README.md`

Added instructions for:

- Running the Textual browser server locally
- Deploying it with the Railway CLI
- Generating a public Railway domain

## Verification Performed

The updated server was tested locally on a temporary port:

```powershell
$env:PORT = "8011"
.\.venv\Scripts\python.exe serve.py
```

The local HTTP request returned status `200`.

Railway successfully:

1. Detected Python and `uv`
2. Installed dependencies from `uv.lock`
3. Started the service with `python serve.py`
4. Served the application on `0.0.0.0:$PORT`
5. Returned HTTP `200` from the public domain

Railway runtime log:

```text
Serving '"/app/.venv/bin/python" main.py' on http://0.0.0.0:8080
```

## Railway CLI

The old Scoop Railway CLI `1.8.3` was removed because its obsolete login
endpoint returned HTTP `404`.

The current npm-installed Railway CLI is:

```text
railway 5.12.1
```

The CLI is authenticated as `larry@chaoticenigma.com`.

Useful commands:

```powershell
railway status
railway logs
railway open
railway up
railway domain
```

## Current Git State

The deployment-related changes are currently uncommitted:

```text
 M README.md
 M serve.py
?? railway.toml
?? CLAUDE_RAILWAY_HANDOFF.md
```

Review and commit these files when ready.

Suggested commit message:

```text
Deploy Textual browser server to Railway
```

## Notes

- `textual-serve` is already included in `pyproject.toml` and `uv.lock`.
- This Railway deployment serves the original Textual application.
- The separate Next.js application under `web/` is unrelated to this Railway
  service.
- A Railway CLI upload created the current deployment. Future deployments can
  use `railway up`, or the service can later be connected to a GitHub branch for
  automatic deployments.
