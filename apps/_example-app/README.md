---
title: Example app
description: Round-trip test for apps; a tiny stdlib Python server run with uv.
---
# Example app

`run.sh` starts `app.py` with `uv run --script` on `$PORT` (from `app.env`).
Caddy serves it at `/_example-app/` and strips the prefix, so the app only ever
sees `/…` paths and must link with relative URLs.

    systemctl --user enable --now lantern-app@_example-app
