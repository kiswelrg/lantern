# lantern — TODO

Work top to bottom. Each phase should end in a working, testable state.

## Phase 0 — Skeleton & install
- [x] Create the directory layout from CLAUDE.md (`bin/`, `systemd/`, `_shared/vendor/`, `sites/`, `apps/`)
- [x] `.gitignore`: `sites/*` and `apps/*` (keep `.gitkeep` and the examples), `lantern.env`, logs.
      Apps are machine-local wrappers like sites; content with no repo goes in `lantern-content`
- [ ] Install Caddy v2 from the official apt repo (Ubuntu's 2.6.2 is too old: templates need
      `readFile`, Caddy ≥ 2.8). Developed and tested against 2.11.7. **Needs sudo** (README → Setup)
- [x] `systemd/lantern.service` (user unit): runs `caddy run --config $LANTERN_ROOT/Caddyfile`,
      sets `LANTERN_ROOT`, `LANTERN_PORT=8080` (override in `lantern.env`)
- [ ] `loginctl enable-linger $USER` so it survives logout/reboot
- [x] Open the port in ufw if enabled: ufw is disabled on this machine; `doctor` warns if that changes

## Phase 1 — Static serving
- [x] Caddyfile: `:{$LANTERN_PORT}`, root `sites/`, `file_server browse`
- [x] `/_shared/*` served from `_shared/`
- [x] Block dotfile paths (404), plus `node_modules/`, `__pycache__/` (also hidden from listings)
- [x] Directory index: `README.md` / `readme.md` / `index.md` for paths ending in `/`, unless `index.html` exists
- [x] `*.md` → `_shared/md.html` + `templates`. The post-rewrite path goes in a server-side
      var (`http.vars.lantern_doc`), not `?doc=`: no query encoding issues, can't be spoofed
- [x] `import {$LANTERN_ROOT}/apps/*/route.caddy` (zero apps only logs a warning)
- [x] Verified: symlinks followed, `readFile` works through symlinks, raw HTML in md passes through,
      relative images/links in docs work. Docs are read with `readFile`, not `include`:
      `include` executes the doc as a template (breaks on `{{ }}`, exposes `env`)
- [x] Smoke tests: `tests/smoke.sh` (30 curl checks)

## Phase 2 — Template & styles
- [x] `md.html`: frontmatter `title` / `style` / `scripts` (+ `description`), sensible fallbacks;
      tolerates a doc that starts with a `---` rule
- [x] `style.css` default: readable width, typography, tables, code blocks, dark mode
- [x] Syntax highlighting: done server-side by Caddy's `markdown` (Chroma classes styled in
      `style.css`), so highlight.js isn't vendored. Revisit only if `.html` showcases need it
- [x] Copy button on every code block (works over plain http via an `execCommand` fallback)
- [x] Vendor mermaid (11.17.2), load only when `scripts: [mermaid]` or the page has a mermaid block
- [x] Small header on every page: link back to `/`, breadcrumbs
- [x] One extra style variant (`paper.css`) to prove switching works
- [x] Sample site `sites/_example` (real folder, committed) exercising everything above
- [x] Styled error pages (404, "app isn't running" for 502)

## Phase 3 — CLI (`bin/lantern`, bash)
- [x] `add-site <name> <path>`: validate name (lowercase-kebab), path exists, no clash → symlink
- [x] `rm-site <name>`: remove symlink only
- [x] `list`: sites (→ target, broken?) and apps (port, unit status)
- [x] `reload`: `caddy validate` then `systemctl --user reload lantern` (→ `caddy reload`)
- [x] `doctor`: caddy version, Caddyfile, units installed/current, running, linger, port, GET /,
      broken symlinks, port collisions, route/app.env port mismatch, missing run.sh, ufw
- [x] `install`: put/refresh units in `~/.config/systemd/user/`, `daemon-reload`, enable/restart

## Phase 4 — Apps
- [x] `systemd/lantern-app@.service`: `WorkingDirectory=$LANTERN_ROOT/apps/%i`,
      `EnvironmentFile=…/app.env`, `ExecStart=…/run.sh`, `Restart=on-failure`, PATH includes `~/.local/bin` (uv)
- [x] `add-app <name> [port]`: scaffold `run.sh` (`uv run --no-project python -m http.server $PORT`),
      `app.env` with next free port in 8101–8199, `route.caddy` = `import lantern-app <name> <port>`
- [x] Example app proving the round trip end to end: `apps/_example-app` (stdlib, `uv run --script`)
- [x] Document the path-prefix requirement for apps (README; apps also get `X-Forwarded-Prefix`, `$BASE_PATH`)
- [ ] Round trip through the real units once Caddy is installed

## Phase 4b — Apps elsewhere, apps on their own port
- [x] Mental model: app **kind** (server / ssh tunnel / proxy, from `app.env`) × **mount**
      (`/<name>/` stripped or kept, or an own LAN port)
- [x] `--own-port` on all three: `port.caddy` site block on 8201–8299, `/<name>/` redirects,
      `HEAD /_status/<name>` for the badge, error page links lantern via `lantern_home`
- [x] `add-tunnel <name> <ssh-host> <host:port>`: generated `run.sh` (`ssh -N -L`, BatchMode)
- [x] `add-proxy <name> <host:port>`: no process, no unit; a 127.0.0.1 upstream keeps the
      visitor's Host (like an app lantern runs)
- [x] `check` / `list` / `doctor` / `rm-app` know the kinds; `check` follows app redirects, takes 401
- [x] Landing page: own-port links, dots for tunnel (green) and proxy (blue) with a legend
- [ ] HTTPS upstreams for `add-proxy` (self-signed: `tls_insecure_skip_verify`)
- [ ] Round trip through the real units: a tunnel once key login to its ssh host works

## Phase 5 — Landing page
- [x] `/` lists all sites and apps (title from README frontmatter / leading `# heading`, else the
      name; `description` from frontmatter), live on every request via `_shared/index.html`
- [x] App up/down badge: client-side `HEAD /_status/<name>` (502 = down), no backend; the route
      drops `WWW-Authenticate` so an app's Basic auth doesn't prompt on the landing page

## Phase 5b — Claude skill (`skill/`)
- [x] CLI groundwork: `add-site --dry-run/--whole-repo` + exposure scan, `new-site`, `check`,
      `rm-app`, `content`, `add-app --keep-prefix` (`(lantern-app-keep)` snippet),
      `install` links `~/.local/bin/lantern` and `~/.claude/skills/lantern`
- [x] Content repo (`lantern-content`, sibling of lantern) for pages/apps with no repo
- [x] Skill: jobs Docs / Blank site / Page / App; survey → one proposal → run → `lantern check` → report
- [x] Smoke tests cover the new CLI on a throwaway copy
- [x] App units read `lantern.env` (proxy vars for uv); `doctor` warns when the shell has a proxy it lacks
- [ ] Cold-start test: trigger the skill from a fresh session in another repo

## Phase 6 — Runnable code (later)
- [ ] Docs on publishing a notebook statically (`jupyter nbconvert --to html`, via `uvx`)
- [ ] In-browser Python: vendor Pyodide under `_shared/vendor/`; try `marimo export html-wasm`
      and/or JupyterLite as a site
- [ ] Server-side kernels only as a sandboxed app: container, no network, CPU/mem limits,
      read-only mounts; prefer fixed widgets over free-form editable cells

## Later / maybe
- [ ] Registry file so sites can be recreated on a new machine (`lantern restore`)
- [ ] Subdomain routing (`<name>.lantern.lan`) for apps that can't live under a path prefix
- [ ] Client-side search across docs
- [ ] Port 80 via system unit with `CAP_NET_BIND_SERVICE`
