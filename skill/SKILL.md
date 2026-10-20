---
name: lantern
description: Publish docs, pages or small web apps on lantern, the LAN docs/app server on this machine. Use when the user wants to host, share or serve a repo's docs, a README, a showcase page or a tool "on lantern" or "on the LAN"; create a blank lantern site; add a page to a lantern site; or make an existing app run under lantern.
---

# lantern

Lantern (Caddy) serves folders and small apps from this machine to the work LAN at
`http://<host>:<port>/<name>/`. The `lantern` CLI does all the mechanics; `lantern help`
lists its commands and `lantern list` shows what is served now. `LANTERN_ROOT` is the parent
of this skill's resolved directory (`readlink -f` it); its `README.md` is the user manual.

## Jobs

Name the job, then read its section before the survey. One request can hold several jobs
(a blank site plus its first pages): survey them together and put them in one proposal.

- **Docs**: an existing folder of docs or a README becomes a site → [sites.md](sites.md) § Existing docs
- **Blank site**: a new, empty site → [sites.md](sites.md) § Blank site
- **Page**: a new `.md` or `.html` page in an existing site → [sites.md](sites.md) § Pages
- **App**: anything that needs a running process → [apps.md](apps.md)

## Steps

1. **Survey.** Work out every value the job needs from the repo and `lantern list`: name,
   folder, prefix mode, run command. The name is the repo or folder name in lowercase-kebab
   unless the user gave one. Run the job's audit. Done when you could run every command
   without asking the user anything.
2. **Proposal.** One message: the name and LAN URL; the commands you will run; the files you
   will create or edit; the **exposure** (below); the audit findings, each with the fix you
   offer. Then wait for the user's go. This is the only confirmation, so make it complete.
3. **Run** exactly what the user accepted.
4. **Check.** `lantern check <name>`, plus `lantern check <name>/<page>` for each page you
   added, must end in `ok`. Fix and re-run until they do; anything still failing goes in the
   report with the error.
5. **Report.** The LAN URL, warnings still open, and the list of files you created or changed
   in other repos and in the content repo, all left uncommitted for the user.

## Rules

- **CLI for mechanics.** Symlinks in `sites/`, the app scaffold, ports, routes and reloads go
  through `lantern`. In `apps/<name>/` you write only `run.sh` and `README.md`. When the CLI
  can't do something the job needs, put that in the report.
- **Exposure.** A linked folder is readable by anyone on the LAN; only dotfiles,
  `node_modules/` and `__pycache__/` are hidden. Link the narrowest folder that holds the
  docs; a repo root (`--whole-repo`) only when the user picks it in the proposal. The proposal
  shows `lantern add-site <name> <dir> --dry-run` output plus your own read of config-like files
  in the folder (`*.json`, `*.yaml`, `*.toml`, `*.ini`, `*.cfg`, `*.conf`): name any tokens,
  passwords, keys or connection strings you find.
- **Offline.** Pages load JS, CSS and fonts from `/_shared/` only; the LAN may have no
  internet. A library missing from `$LANTERN_ROOT/_shared/vendor/` is vendored there (steps in
  its `README.md`) once the user accepts it in the proposal.
- **Uncommitted.** Every change stays in the working tree of its repo; the user commits.
- **Runtimes.** Python runs through `uv`; other languages only through the toolchain the app
  already uses.
- **Content repo.** Pages and tools that belong to no repo live in the content repo:
  `lantern content` prints its path and creates it on first use.
