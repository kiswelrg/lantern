# lantern

Docs, READMEs, showcases and small tools from all my repos, served on the LAN.

Open `http://<this-machine>:8080/` to see everything that's hosted.

`bin/lantern install` puts the CLI on your PATH as `lantern` (a symlink in `~/.local/bin`).

## Add a doc
Point lantern at a folder inside any repo:

```bash
lantern add-site deploy-notes ~/Projects/some-repo/docs --dry-run   # what becomes readable on the LAN
lantern add-site deploy-notes ~/Projects/some-repo/docs
# -> http://<host>:8080/deploy-notes/
lantern check deploy-notes    # index answers, README renders, links on it resolve
```

That's it, no config edits and no restart. It's just a symlink in `sites/`.
`add-site` lists the file count and any risky-looking files (keys, `*.env`, databases, …) and
refuses a whole repo root unless you pass `--whole-repo`: link the docs folder instead.

New, empty site: `lantern new-site <name> [dir]` creates `dir` with a stub `README.md` and
links it. Without a `dir` it goes in the **content repo** (below).

- Write docs in **Markdown**. They're rendered with the shared style automatically,
  with server-side syntax highlighting and a copy button on every code block.
- A folder's `README.md` (or `readme.md`, `index.md`) becomes its index page, unless the
  folder has an `index.html`. Folders with neither get a file listing.
- Need custom layout or interactivity? Write a `.html` file in the same folder and add
  `<link rel="stylesheet" href="/_shared/style.css">`.
- Relative links and images (`./img.png`, `other.md`) just work.
- Never put secrets in a hosted folder. Dotfiles (`.git`, `.env`, …), `node_modules/` and
  `__pycache__/` return 404, but everything else in the folder is readable on the LAN.

`sites/_example/` shows every feature; open `/_example/` once lantern is running.

### Optional frontmatter
```markdown
---
title: Deploy notes   # <title>, heading, landing-page card; fallback: first "# heading", then the file name
description: How we deploy   # shown on the landing page (README only)
style: paper          # use /_shared/paper.css instead of the default
scripts: [mermaid]    # load extra vendored scripts for this page
---
```

```` ```mermaid ```` blocks load mermaid automatically, so `scripts: [mermaid]` is optional.

## Add an app
For something that needs a running process (Flask, Streamlit, a small Node server):

```bash
lantern add-app my-tool            # creates apps/my-tool/ with run.sh, app.env, route.caddy, README.md
# edit apps/my-tool/run.sh to start your server on $PORT (127.0.0.1)
systemctl --user enable --now lantern-app@my-tool
lantern check my-tool
# -> http://<host>:8080/my-tool/
```

`add-app` picks the next free port in 8101–8199 and reloads Caddy if it's running (otherwise
run `lantern reload` once it is). `apps/<name>/` is a machine-local wrapper (gitignored,
like `sites/`): the app's code stays in its own repo, and `run.sh` points at it.
`lantern rm-app my-tool` stops and disables the unit and removes the wrapper.

Apps live under `/my-tool/` and Caddy strips that prefix, so **apps must use relative URLs**
(`href="static/app.css"`, `fetch("api/x")`). If an app needs absolute URLs, it gets the
prefix in `$BASE_PATH` and in the `X-Forwarded-Prefix` request header (e.g. Flask with
`ProxyFix(x_prefix=1)`, uvicorn `--root-path /my-tool`, Gradio `GRADIO_ROOT_PATH`).
Apps that serve under a base path themselves (Streamlit `--server.baseUrlPath`,
marimo `--base-url`, Dash `url_base_pathname`) need the prefix kept:
`lantern add-app my-tool --keep-prefix`.

Python apps use **uv**: a single-file app with PEP 723 metadata runs with
`exec uv run --script app.py`; an app in another repo with
`exec uv run --project /path/to/repo …`. `apps/_example-app/` is a working example.

Logs: `journalctl --user -u lantern-app@my-tool -f`.

App units don't see your shell's environment. If you reach the internet through a proxy, put
`HTTP_PROXY`, `HTTPS_PROXY` and `NO_PROXY` in `lantern.env` (every app unit reads it), or the
first start hangs while uv downloads dependencies. `lantern doctor` warns about this.

## Content repo
Pages and small tools that don't belong to any repo live in a separate git repo,
`lantern-content` next to lantern (set `LANTERN_CONTENT=` in `lantern.env` to move it).
`lantern content` prints its path and creates it on first use:

- `pages/<name>/`: a site (`lantern new-site <name>` creates one and links it)
- `apps/<name>/`: code for a self-contained app; lantern's `apps/<name>/run.sh` starts it

Commit there as you like; lantern itself only holds the infrastructure.

## With Claude Code
`bin/lantern install` links the `lantern` skill (`skill/`) into `~/.claude/skills/`, so in any
repo you can ask Claude to "put these docs on lantern", "make a blank lantern site", "add a
page to the X site" or "run this app under lantern". It surveys, shows one proposal (name,
commands, what becomes readable on the LAN, audit findings), runs it after your go, and
finishes with `lantern check`. It never commits.

## Styles
All shared CSS lives in `_shared/`. Edit `style.css` to change the default look everywhere
(it has light and dark variants), or add a variant like `paper.css` (it `@import`s
`style.css` and overrides a few variables) and select it per page with `style: paper`.

## Other commands
```bash
lantern list           # sites and apps, with targets / ports / status
lantern check X        # live check of one site or app
lantern rm-site X      # remove a site (deletes the symlink only)
lantern rm-app X       # stop + disable an app, remove apps/X/ (--force if it holds other files)
lantern doctor         # caddy, service, port, broken links, port clashes
lantern reload         # validate + reload Caddy (only needed for new apps)
tests/smoke.sh         # curl + CLI smoke tests on a throwaway copy (or: tests/smoke.sh http://host:8080)
```

## Setup (once)
Needs **Caddy ≥ 2.8** (developed against 2.11.7). Ubuntu's own `caddy` package is too old
(2.6), so use Caddy's official apt repo (https://caddyserver.com/docs/install#debian-ubuntu-raspbian):

```bash
sudo apt install --yes debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
sudo chmod o+r /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy
sudo systemctl disable --now caddy    # the package's own system service (port 80); lantern runs its own
```

Then, as yourself:

```bash
bin/lantern install            # user units -> ~/.config/systemd/user, starts lantern on :8080
                               # (--port N to change; saved in lantern.env); links
                               # ~/.local/bin/lantern and ~/.claude/skills/lantern
loginctl enable-linger $USER   # keep running after logout / across reboots
bin/lantern doctor
```

If ufw is enabled, allow the port from the LAN only, e.g.
`sudo ufw allow from 192.168.1.0/24 to any port 8080 proto tcp`.

Port 80 instead of 8080 would need a system unit with `CAP_NET_BIND_SERVICE`; not set up.
