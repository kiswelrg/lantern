# lantern — context for Claude Code

## What this is
A single place on an Ubuntu machine on the **work LAN** that serves docs, READMEs,
instructions and showcases from many repos (long-lived and one-off), plus the
occasional small web app, so colleagues can open them in a browser.

It replaces ad-hoc `python -m http.server` / small Flask servers run in separate terminals.

**Core principle: configure once, add by convention.** Adding a new doc or app must
never require editing the Caddyfile, writing a new systemd unit, or touching a backend.
Adding a doc = create a symlink. Adding an app = drop a folder + one enable command.

## Architecture (decided)
- **Caddy v2** is the only server. No Django, no Node backend, no frontend framework.
- **Static docs** live in each repo; `sites/<name>` is a symlink to that repo's docs folder.
  URL: `http://<host>:<port>/<name>/`. Pages and tools that belong to no repo live in the
  **content repo** (`lantern-content`, sibling of lantern; `LANTERN_CONTENT` in `lantern.env`
  overrides): `pages/<name>/` linked from `sites/`, `apps/<name>/` holding app code.
- **Markdown is the default doc format.** `.md` requests are rendered server-side via Caddy
  `templates` + `_shared/md.html` (uses `readFile`, `splitFrontMatter`, `markdown`).
  Never `include` a doc: it executes the doc as a template (breaks on `{{ }}`, exposes `env`).
  Code is highlighted server-side by Caddy's markdown (Chroma classes, styled in `style.css`).
  `.html` files are served as-is (for showcases needing layout/interactivity).
- **One shared look:** stylesheets in `_shared/` (`style.css` default, more variants allowed).
  A doc picks one via frontmatter `style: <name>`; HTML pages link `/_shared/<name>.css`.
- **Apps** (anything lantern reverse-proxies): `apps/<name>/` is a machine-local wrapper
  (gitignored like `sites/`) with `app.env`, `route.caddy`, `README.md` (landing card) and,
  when something runs, `run.sh`; the app's code lives in its own repo or the content repo.
  `app.env` says the **kind**: a server (`add-app`, `PORT`) or an ssh tunnel (`add-tunnel`,
  `PORT` + `TUNNEL_VIA`/`TUNNEL_TO`, run.sh is `ssh -N -L`), both run by ONE systemd user
  template unit `lantern-app@.service`; or a proxy (`add-proxy`, `UPSTREAM`; nothing runs, no
  unit; a `127.0.0.1` upstream is routed with the `lantern-app` snippets). The **mount**: `/<name>/` with the prefix stripped (`(lantern-app)`/`(lantern-proxy)`)
  or kept (`--keep-prefix`, the `-keep` snippets), both via the Caddyfile
  `import apps/*/route.caddy` glob inside the main site; or the app's **own port**
  (`--own-port`, `LAN_PORT`): `port.caddy` (top-level `import apps/*/port.caddy`,
  `(lantern-own-port-site)`) serves it at `/`, and its `route.caddy` (`(lantern-own-port)`)
  redirects `/<name>/` there; both take the upstream's Host header as their last argument
  (`{hostport}` or `{upstream_hostport}`). Every app snippet also answers `HEAD /_status/<name>`
  on the main port: the landing page's up/down badge.
- **Directories** with a `README.md` (or `readme.md`, `index.md`) render it as the index, unless
  they have an `index.html`; otherwise Caddy `browse` listing via `_shared/browse.html`.
- **Landing page** `/` is `_shared/index.html`, a template that lists `sites/` and `apps/` live;
  app cards read `app.env` (own-port link, green dot = tunnel, blue dot = proxy). Doc cards
  open in the same tab, app cards in a new tab.
- **Caddy ≥ 2.8** required (`readFile`); developed against 2.11.7. Ubuntu's apt package (2.6) is too old.

## Layout
```
lantern/
├── CLAUDE.md  README.md  TODO.md
├── Caddyfile              # written once; uses {$LANTERN_ROOT}, {$LANTERN_PORT}
├── bin/lantern            # bash CLI (`lantern help`); install links it as ~/.local/bin/lantern
├── skill/                 # Claude skill `lantern` (SKILL.md, sites.md, apps.md); install links
│                          #   it as ~/.claude/skills/lantern
├── tests/smoke.sh         # curl + CLI smoke tests (throwaway copy of lantern, or a URL)
├── lantern.env            # optional, gitignored: LANTERN_PORT, LANTERN_CONTENT, proxy vars (read by all units)
├── systemd/
│   ├── lantern.service          # runs caddy
│   └── lantern-app@.service     # template unit for all apps
├── _shared/
│   ├── md.html            # markdown page template
│   ├── index.html         # landing page template (lists sites/ and apps/)
│   ├── browse.html        # directory listing template
│   ├── error.html         # error page template (handle_errors)
│   ├── lantern.js         # copy buttons, heading anchors, mermaid init, app up/down badges
│   ├── style.css          # default style (+ variants like paper.css that @import it)
│   └── vendor/            # mermaid, etc. — vendored, NO CDN (versions in vendor/README.md)
├── sites/                 # symlinks only (gitignored except .gitkeep and _example/)
└── apps/<name>/{run.sh, app.env, route.caddy, port.caddy, README.md}   # gitignored; _example-app/ is committed
../lantern-content/        # separate git repo: pages/<name>/, apps/<name>/ (created on first use)
```

## Doc frontmatter (all optional)
```yaml
---
title: Deploy notes        # <title> and page heading; fallback = leading "# h1", then filename
style: paper               # -> /_shared/paper.css; fallback = style
scripts: [mermaid]         # extra vendored scripts -> /_shared/vendor/<name>.min.js
description: One line      # landing-page card text (README only)
---
```
Mermaid also auto-loads when the body contains a ```` ```mermaid ```` block.

## Conventions / constraints
- Never hardcode the user's home path. Scripts derive `LANTERN_ROOT` from their own location;
  units/config use env vars or are generated by `bin/lantern` at install time. (Machine-local,
  gitignored files like `apps/<name>/run.sh` may hold absolute paths to other repos.)
- **The skill follows the CLI.** `skill/*.md` drives `bin/lantern` and caches some of its
  behaviour: when a command, flag or convention changes, update `skill/`, README.md and
  `tests/smoke.sh` in the same change. Mechanics belong in the CLI, judgment in the skill.
- Default run mode: Caddy as a **systemd user service** on a high port (default `8080`),
  so it can read files under `$HOME` directly. Requires `loginctl enable-linger $USER`.
  Port 80 is optional (system unit with `User=` + `CAP_NET_BIND_SERVICE`) — ask before doing it.
- Site address must be `:PORT` / `http://` so Caddy does NOT attempt automatic HTTPS.
- App ports: allocate from `8101–8199` (where apps listen on 127.0.0.1) and, for `--own-port`,
  `8201–8299` (where Caddy serves them to the LAN); the CLI picks the next free one and writes
  `app.env`.
- Work LAN may have unreliable internet: vendor all JS/CSS/fonts into `_shared/vendor/`.
- Keep it boring: bash + Caddyfile + plain HTML/CSS/JS. Ask before adding a language runtime
  or build step.
- Any Python (apps, tooling) goes through **uv**: `uv run --script` (PEP 723) or
  `uv run --project …`; the app unit puts `~/.local/bin` on PATH for it.
- Caddy templates are `text/template`: no auto-escaping. Escape with `html` in our templates.

## Gotchas to handle
- **Hide dotfiles**: a symlinked repo may contain `.git/`, `.env`, etc. Return 404 for any
  path segment starting with `.` (and consider `node_modules/`, `__pycache__/`).
- **Rewrite ordering**: the README rewrite must run before the `*.md` handler, and the template
  must read the *post-rewrite* path. Solved with `vars lantern_doc {path}` inside the md handle
  (read via `placeholder "http.vars.lantern_doc"`), not `?doc=` (encoding issues, spoofable).
- **Directive ordering**: the whole site sits in one `route {}` so it runs top to bottom.
  Outside a route, Caddy sorts `handle` before `handle_path`, and a catch-all `handle` would
  swallow the apps' `handle_path` routes.
- Verified: `file_server` and `readFile` follow symlinks; Caddy's `markdown` passes raw HTML through.
- A doc starting with a `---` rule is not frontmatter: md.html only calls `splitFrontMatter` when
  the fence is closed. Invalid YAML frontmatter still gives a 500 (error page shows the message).
- `navigator.clipboard` doesn't exist over plain http on the LAN; lantern.js falls back to `execCommand`.
- Relative links/images inside docs must keep working (`./img.png`, `other.md`).
- **Apps under a path prefix** break if they assume `/` (absolute asset URLs). The
  `(lantern-app)` snippet uses `handle_path` and sends `X-Forwarded-Prefix`; the unit sets
  `BASE_PATH`. Apps must use relative URLs or a configurable base path. Frameworks that serve
  under a base path themselves (Streamlit, marimo, Dash) use `(lantern-app-keep)` instead;
  Gradio and uvicorn's `--root-path` expect the prefix stripped. Apps that can't be told a
  base path (device UIs, vendor dashboards) use `--own-port`.
  Subdomain routing (wildcard DNS) is a later option, not now.
- **Own port**: cookies are scoped per host, not per port, so own-port apps share cookies with
  each other (same cookie name = they log each other out). The landing page can't read a
  cross-origin status, hence `HEAD /_status/<name>` on the main port, for every app. On an own
  port `/` is the app's, so `error.html` links lantern through `vars lantern_home`.
- **Badge and Basic auth**: a same-origin fetch that gets `401` + `WWW-Authenticate: Basic`
  makes the browser show a login dialog, on the landing page. The `/_status/<name>` route
  drops that header (`header_down -WWW-Authenticate`); a 401 there still counts as up. It asks
  the app with `GET` (`method GET`): Python's `BaseHTTPRequestHandler` apps answer HEAD with 501.
- Caddy's `reverse_proxy` honours `HTTP_PROXY`/`NO_PROXY` (lantern.service reads `lantern.env`):
  a non-loopback upstream (`add-proxy`) goes through the proxy unless `NO_PROXY` covers it.
  A remote upstream must get `Host: {upstream_hostport}`: with the visitor's Host, the local
  proxy (mihomo) routed the request back to Caddy (431, a stack of `Via: 1.1 Caddy`). Anything
  on 127.0.0.1 (servers, tunnels, local proxies) keeps the visitor's Host: apps check it
  (relabel's `--allowed-host`) and build URLs from it. So `lantern check` requests the LAN
  address, as colleagues do, with `--noproxy '*'`.
- Caddyfile snippets must not import other snippets: a snippet that does mis-parses once it
  is imported twice ("wrong argument count … after '302'"). Write each one out in full.
- Tunnels under systemd have no terminal and no agent: run.sh uses `BatchMode=yes`,
  `ExitOnForwardFailure=yes`, `ServerAlive*` (a dead link exits, the unit restarts it) and
  `StrictHostKeyChecking=accept-new`. Key login is the user's one-time setup (`ssh-copy-id`).
- Linux paths are case-sensitive; URL/site names should be lowercase-kebab.
- systemd user units don't inherit the shell's environment: no proxy variables (uv's first-start
  downloads hang; they go in `lantern.env`, which every app unit reads) and a minimal PATH (uv
  may pick a different Python than your shell, so the shell's cached wheels don't apply).

## Verifying changes
- `caddy validate --config Caddyfile` (with env vars set) before reloading; `bin/lantern reload` does this.
- `tests/smoke.sh` runs the curl checks below on a throwaway copy of lantern (port 18080,
  admin 12019), plus CLI tests there with systemd cut off; it never touches the real
  `sites/`, `apps/`, content repo or units.
- `lantern check <name>` is the live check for one site or app (the skill's done-criterion).
- `bin/lantern doctor` should check: caddy installed/running, port listening, broken symlinks,
  apps with missing PORT or port collisions.
- Smoke test with `curl`: a `.md` renders as HTML with the stylesheet link; a dir with
  README renders it; a `.html` is served raw; `/<site>/.git/config` returns 404;
  an app route proxies; an own-port app answers at its root and `/<name>/` redirects there.

## Future (don't build yet — see TODO.md)
Runnable code blocks: copy button (frontend only) → in-browser Python via Pyodide /
`marimo export html-wasm` / JupyterLite (static, fits `sites/`) → server kernels
(Jupyter + Thebe, Voilà, `marimo run`) as a sandboxed app in `apps/` (container, no network,
resource limits) because it is arbitrary code execution on a work machine.
