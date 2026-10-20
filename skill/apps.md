# Apps

An app is a process lantern proxies at `/<name>/`. Lantern's `apps/<name>/` is a machine-local
wrapper (gitignored): `run.sh` (start command), `app.env` (`PORT`), `route.caddy` and
`README.md` (landing card: `title`, `description`). The systemd user unit
`lantern-app@<name>` runs `run.sh` from that folder with `PORT`, `APP_NAME` and
`BASE_PATH=/<name>/` set. `$LANTERN_ROOT/apps/_example-app/` is a working example.

A frontend that builds to static files is a site, not an app: build it with a relative base
(Vite `base: './'`) and link the build folder ([sites.md](sites.md)).

A tool that lets visitors run code (Jupyter, `marimo edit`, a shell, an eval endpoint) is out
of scope: tell the user it waits on the sandboxed setup in lantern's `TODO.md` (Phase 6).

## Survey

- **Entry point**: how the user runs it today (README, Makefile, scripts, `pyproject.toml`,
  `package.json`).
- **Run command**, bound to `127.0.0.1:$PORT`:
  - Python goes through uv: `uv run --project <repo> …` (has `pyproject.toml`),
    `uv run --with-requirements <repo>/requirements.txt …`, or `uv run --script app.py`
    (single file with a PEP 723 header).
  - Other languages: the app's own toolchain, already installed.
- **Load**: heavy dependencies (torch, CUDA, large models) go in the proposal with their
  RAM/GPU cost; the machine is shared.
- **Secrets**: env files stay in the app's repo; `run.sh` sources them
  (`set -a; . <repo>/.env; set +a`).
- **Prefix mode**: from the table below.
- **Absolute URLs**: grep templates, static files and JS for root-relative URLs (`href="/`,
  `src="/`, `action="/`, `fetch("/`, redirects to `"/…"`). In strip mode each one leaves
  `/<name>/` unless the framework adds the prefix itself.
- **Home**: an app with no repo of its own keeps its code in `$(lantern content)/apps/<name>/`.

Prefer fixes in `run.sh` (flags, env, a wrapper) over edits to the app; show any code edit as
a diff in the proposal.

## Prefix

- **strip** (`lantern add-app <name>`): Caddy removes `/<name>`; the app sees `/…` and gets
  the prefix in `X-Forwarded-Prefix`. For apps with relative URLs, or apps told their root path.
- **keep** (`lantern add-app <name> --keep-prefix`): the app sees the full `/<name>/…`. For
  frameworks that serve under a configured base path themselves.

| Framework | Mode | In `run.sh` |
|---|---|---|
| Flask / Werkzeug | strip | `ProxyFix(app.wsgi_app, x_prefix=1)` so `url_for` adds the prefix (wrapper below) |
| FastAPI / Starlette | strip | `uvicorn mod:app --host 127.0.0.1 --port "$PORT" --root-path "/$APP_NAME"` |
| Gradio | strip | env `GRADIO_ROOT_PATH="/$APP_NAME" GRADIO_SERVER_NAME=127.0.0.1 GRADIO_SERVER_PORT="$PORT"`, when `launch()` doesn't hardcode them |
| Streamlit | keep | `streamlit run app.py --server.address 127.0.0.1 --server.port "$PORT" --server.baseUrlPath "$APP_NAME" --server.headless true` |
| marimo (`run`) | keep | `marimo run app.py --host 127.0.0.1 --port "$PORT" --base-url "/$APP_NAME" --headless` |
| Dash | keep | env `DASH_URL_BASE_PATHNAME="$BASE_PATH"`, server on `127.0.0.1:$PORT` |
| Django (gunicorn) | keep | env `SCRIPT_NAME="/$APP_NAME"`; `STATIC_URL` under the prefix |
| anything else | strip | relative URLs only |

Flask wrapper, all inside `run.sh`:

```bash
cd /path/to/repo
exec uv run --project . python - <<'PY'
import os
from werkzeug.middleware.proxy_fix import ProxyFix
from app import app  # the repo's Flask app object
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)
app.run(host="127.0.0.1", port=int(os.environ["PORT"]))
PY
```

## Run

1. `lantern add-app <name>`, with `--keep-prefix` for keep mode.
2. Write `apps/<name>/run.sh`: keep its header comment, `set -euo pipefail`, `cd` to the app,
   `exec` the server. Fill `title`/`description` in `apps/<name>/README.md`.
3. `systemctl --user enable --now lantern-app@<name>`. A first start can take minutes while
   uv installs dependencies: re-run `lantern check <name>` until the app answers, and read
   `journalctl --user -u lantern-app@<name> -n 50` when it doesn't. Units don't see the
   shell's environment: a start stuck on `Downloading …` while the shell has `HTTPS_PROXY`
   set means those proxy variables belong in `$LANTERN_ROOT/lantern.env` (`lantern doctor`
   flags it); add them in the proposal, then `systemctl --user restart lantern-app@<name>`.
4. `lantern rm-app <name>` undoes it all (unit stopped and disabled, wrapper removed).
