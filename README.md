# lantern

Docs, READMEs, showcases and small tools from all my repos, served on the LAN.

Open `http://<this-machine>:8080/` to see everything that's hosted.

## Add a doc
Point lantern at a folder inside any repo:

```bash
bin/lantern add-site deploy-notes ~/Projects/some-repo/docs
# -> http://<host>:8080/deploy-notes/
```

That's it, no config edits and no restart. It's just a symlink in `sites/`.

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
For something that needs a running process (Flask, a small Node server, a notebook app):

```bash
bin/lantern add-app my-tool        # creates apps/my-tool/ with run.sh, app.env, route.caddy
# edit apps/my-tool/run.sh to start your server on $PORT (127.0.0.1)
systemctl --user enable --now lantern-app@my-tool
# -> http://<host>:8080/my-tool/
```

`add-app` picks the next free port in 8101–8199 and reloads Caddy if it's running (otherwise
run `bin/lantern reload` once it is).

Apps live under `/my-tool/` and Caddy strips that prefix, so **apps must use relative URLs**
(`href="static/app.css"`, `fetch("api/x")`). If an app needs absolute URLs, it gets the
prefix in `$BASE_PATH` and in the `X-Forwarded-Prefix` request header (e.g. Flask with
`ProxyFix(x_prefix=1)`).

Python apps use **uv**: a single-file app with PEP 723 metadata runs with
`exec uv run --script app.py`; an app in another repo with
`exec uv run --project /path/to/repo …`. `apps/_example-app/` is a working example.

Logs: `journalctl --user -u lantern-app@my-tool -f`.

## Styles
All shared CSS lives in `_shared/`. Edit `style.css` to change the default look everywhere
(it has light and dark variants), or add a variant like `paper.css` (it `@import`s
`style.css` and overrides a few variables) and select it per page with `style: paper`.

## Other commands
```bash
bin/lantern list       # sites and apps, with targets / ports / status
bin/lantern rm-site X  # remove a site (deletes the symlink only)
bin/lantern doctor     # caddy, service, port, broken links, port clashes
bin/lantern reload     # validate + reload Caddy (only needed for new apps)
tests/smoke.sh         # curl smoke tests on a throwaway Caddy (or: tests/smoke.sh http://host:8080)
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
                               # (--port N to change; saved in lantern.env)
loginctl enable-linger $USER   # keep running after logout / across reboots
bin/lantern doctor
```

If ufw is enabled, allow the port from the LAN only, e.g.
`sudo ufw allow from 192.168.1.0/24 to any port 8080 proto tcp`.

Port 80 instead of 8080 would need a system unit with `CAP_NET_BIND_SERVICE`; not set up.
