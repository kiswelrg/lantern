# Apps

An app is anything lantern reverse-proxies. Lantern's `apps/<name>/` is a machine-local
wrapper (gitignored): `app.env`, `route.caddy`, `README.md` (landing card: `title`,
`description`), plus `run.sh` when something runs and `port.caddy` for an app on its own
port. The systemd user unit `lantern-app@<name>` runs `run.sh` from that folder with
`PORT`, `APP_NAME` and `BASE_PATH=/<name>/` set (`/` on its own port).
`$LANTERN_ROOT/apps/_example-app/` is a working example.

A frontend that builds to static files is a site, not an app: build it with a relative base
(Vite `base: './'`) and link the build folder ([sites.md](sites.md)).

A tool that lets visitors run code (Jupyter, `marimo edit`, a shell, an eval endpoint) is out
of scope: tell the user it waits on the sandboxed setup in lantern's `TODO.md` (Phase 6).

## Kind

Pick one; each is one command.

- **Server** (`lantern add-app <name>`): lantern runs it; you write `run.sh`. Everything from
  § Survey on is about this kind.
- **Tunnel** (`lantern add-tunnel <name> <ssh-host> <host:port>`): a service only reachable
  through ssh. `<host:port>` is the target as the ssh host sees it; `<ssh-host>` is
  `user@host`, `ssh://user@host:port`, or a `Host` alias from `~/.ssh/config` (prefer an
  alias that already matches). The CLI writes `run.sh` (an `ssh -N -L` forward). The unit has
  no terminal or agent, so `ssh -o BatchMode=yes <ssh-host> true` must succeed: if it doesn't,
  the user runs `ssh-copy-id` themselves (it asks for their password: never ask for it,
  store it, or script it).
- **Proxy** (`lantern add-proxy <name> <host:port>`): a plain-HTTP service lantern doesn't
  start: one elsewhere that this machine reaches directly (`curl -sI http://<host:port>/`
  answers), or one already running here that the user keeps running themselves
  (`127.0.0.1:<port>`, routed like a local app). Nothing runs, no unit, nothing restarts it:
  for a process on this machine, offer a server (`add-app`) instead. An HTTPS upstream isn't
  supported by the CLI: say so in the report.

## Mount

- **strip** (default): served at `/<name>/`, Caddy removes the prefix; the app sees `/…` and
  gets the prefix in `X-Forwarded-Prefix`. For apps with relative URLs, or apps told their root.
- **keep** (`--keep-prefix`): served at `/<name>/` with the full path passed through. For
  frameworks that serve under a configured base path themselves.
- **own port** (`--own-port`): served at the root of `http://<host>:<lan-port>/`, port from
  8201–8299; `/<name>/` redirects there. For apps that need `/` and can't be told otherwise:
  device and vendor web UIs (cameras, NVRs, routers, admin dashboards), SPAs built with base
  `/`. Usually right for tunnels and proxies.

Survey a service you can't change: `curl -s http://<upstream>/ | grep -oE '(href|src|action)="/[^"]*"'`
and `curl -sI` for a `Location: /…` redirect. Any hit means own port. For a tunnel target,
run the same through ssh (`ssh <ssh-host> curl -s http://<host:port>/`) when the user's key
login already works; otherwise default to own port. Browsers share cookies across the ports
of one host: two apps on their own ports that use the same cookie name (two cameras of one
model) log each other out. Mention it when that applies.

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
- **Mount**: from § Mount and the table below.
- **Absolute URLs**: grep templates, static files and JS for root-relative URLs (`href="/`,
  `src="/`, `action="/`, `fetch("/`, redirects to `"/…"`). In strip mode each one leaves
  `/<name>/` unless the framework adds the prefix itself; when there's no flag for it, use
  `--own-port`.
- **Home**: an app with no repo of its own keeps its code in `$(lantern content)/apps/<name>/`.

Prefer fixes in `run.sh` (flags, env, a wrapper) over edits to the app; show any code edit as
a diff in the proposal.

| Framework | Mode | In `run.sh` |
|---|---|---|
| Flask / Werkzeug | strip | `ProxyFix(app.wsgi_app, x_prefix=1)` so `url_for` adds the prefix (wrapper below) |
| FastAPI / Starlette | strip | `uvicorn mod:app --host 127.0.0.1 --port "$PORT" --root-path "/$APP_NAME"` |
| Gradio | strip | env `GRADIO_ROOT_PATH="/$APP_NAME" GRADIO_SERVER_NAME=127.0.0.1 GRADIO_SERVER_PORT="$PORT"`, when `launch()` doesn't hardcode them |
| Streamlit | keep | `streamlit run app.py --server.address 127.0.0.1 --server.port "$PORT" --server.baseUrlPath "$APP_NAME" --server.headless true` |
| marimo (`run`) | keep | `marimo run app.py --host 127.0.0.1 --port "$PORT" --base-url "/$APP_NAME" --headless` |
| Dash | keep | env `DASH_URL_BASE_PATHNAME="$BASE_PATH"`, server on `127.0.0.1:$PORT` |
| Django (gunicorn) | keep | env `SCRIPT_NAME="/$APP_NAME"`; `STATIC_URL` under the prefix |
| anything else | strip | relative URLs only; own port when it hardcodes `/` |

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

## Exposure

A tunnel or a proxy to another host puts a service from elsewhere on the LAN, and lantern
adds no login of its own. The proposal names the service, whether it has its own login, and
that anyone who can reach lantern can reach it. Caddy sends requests to a non-loopback
upstream through `HTTP_PROXY` in `$LANTERN_ROOT/lantern.env` unless `NO_PROXY` covers its
host: when lantern.env sets a proxy, say which way the upstream will go.

## Run

1. The kind's command, with the mount flag.
2. Server: write `apps/<name>/run.sh` (keep its header comment, `set -euo pipefail`, `cd` to
   the app, `exec` the server). Tunnel and proxy: leave `run.sh` as written. Every kind: fill
   `title`/`description` in `apps/<name>/README.md`.
3. Server and tunnel: `systemctl --user enable --now lantern-app@<name>`. A first start can
   take minutes while uv installs dependencies: re-run `lantern check <name>` until the app
   answers, and read `journalctl --user -u lantern-app@<name> -n 50` when it doesn't. Units
   don't see the shell's environment: a start stuck on `Downloading …` while the shell has
   `HTTPS_PROXY` set means those proxy variables belong in `$LANTERN_ROOT/lantern.env`
   (`lantern doctor` flags it); add them in the proposal, then
   `systemctl --user restart lantern-app@<name>`. A tunnel that won't come up is almost
   always key login: `ssh -o BatchMode=yes <ssh-host> true`.
4. `lantern check <name>`: a `401` (the app's own login) counts as answering.
5. `lantern rm-app <name>` undoes it all (unit stopped and disabled, wrapper removed).
