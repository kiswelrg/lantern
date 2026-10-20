#!/usr/bin/env bash
# Started by lantern-app@_example-app.service with PORT (app.env), APP_NAME and BASE_PATH set.
set -euo pipefail
cd "$(dirname "$0")"
exec uv run --script app.py
