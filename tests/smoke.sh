#!/usr/bin/env bash
# Smoke tests for lantern (curl only).
#
#   tests/smoke.sh                       start a throwaway Caddy on a spare port and test it
#   tests/smoke.sh http://localhost:8080 test a running instance
#
# Uses sites/_example and apps/_example-app, plus a temporary symlinked "repo"
# (sites/_smoke) to check that .git etc. are blocked. Starts the example app for
# the duration of the test if nothing is listening on its port yet.
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
BASE="${1:-}"
TMP="$(mktemp -d)"
PIDS=()
cleanup() {
  local p
  for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done
  rm -f "$ROOT/sites/_smoke"
  rm -rf "$TMP"
}
trap cleanup EXIT

wait_for() { # url
  local i
  for i in $(seq 50); do curl -s -o /dev/null "$1" && return 0; sleep 0.2; done
  echo "timed out waiting for $1" >&2
  return 1
}

if [[ -z "$BASE" ]]; then
  command -v caddy >/dev/null || { echo "caddy not on PATH" >&2; exit 1; }
  export LANTERN_ROOT="$ROOT" LANTERN_PORT=18080 LANTERN_ADMIN_PORT=12019
  caddy run --config "$ROOT/Caddyfile" --adapter caddyfile >"$TMP/caddy.log" 2>&1 &
  PIDS+=($!)
  BASE="http://127.0.0.1:$LANTERN_PORT"
  wait_for "$BASE/" || { cat "$TMP/caddy.log" >&2; exit 1; }
fi
BASE="${BASE%/}"

APP_PORT="$(sed -n 's/^PORT=//p' "$ROOT/apps/_example-app/app.env")"
if ! ss -Htln | awk '{print $4}' | grep -q ":$APP_PORT\$"; then
  (cd "$ROOT/apps/_example-app" && PORT="$APP_PORT" APP_NAME=_example-app exec ./run.sh) >"$TMP/app.log" 2>&1 &
  PIDS+=($!)
  wait_for "http://127.0.0.1:$APP_PORT/" || { cat "$TMP/app.log" >&2; exit 1; }
fi

# A fake repo with things that must never be served.
mkdir -p "$TMP/repo/.git" "$TMP/repo/node_modules/x" "$TMP/repo/__pycache__" "$TMP/repo/docs"
echo "[core]" >"$TMP/repo/.git/config"
echo "SECRET=1" >"$TMP/repo/.env"
echo "x" >"$TMP/repo/node_modules/x/index.js"
echo "x" >"$TMP/repo/__pycache__/m.pyc"
printf -- '---\n\nDoc that starts with a rule.\n' >"$TMP/repo/docs/rule.md"
printf '# Smoke repo\n' >"$TMP/repo/README.md"
ln -sfn "$TMP/repo" "$ROOT/sites/_smoke"

pass=0 failed=0
check() { # description, then a command that must succeed
  local desc=$1
  shift
  if "$@" >/dev/null 2>&1; then
    pass=$((pass + 1))
  else
    failed=$((failed + 1))
    echo "FAIL: $desc"
  fi
}
status() { [[ "$(curl -s -o /dev/null -w '%{http_code}' "$BASE$1")" == "$2" ]]; }
has() { curl -s "$BASE$1" | grep -qF -- "$2"; }
lacks() { ! curl -s "$BASE$1" | grep -qF -- "$2"; }
ctype() { curl -s -o /dev/null -w '%{content_type}' "$BASE$1" | grep -q "^$2"; }

check "landing page lists the example site"   has / 'lantern example'
check "landing page lists the example app"     has / 'data-app-status="/_example-app/"'
check "dir with README renders it"             has /_example/ '<h1 id="lantern-example">'
check "rendered md links the stylesheet"       has /_example/ '<link rel="stylesheet" href="/_shared/style.css">'
check ".md is rendered as HTML"                ctype /_example/features.md text/html
check "code is highlighted"                    has /_example/features.md 'class="chroma"'
check "{{ }} in docs is not executed"          has /_example/features.md '{{ .Values.image.repository }}'
check "raw HTML passes through"                has /_example/features.md '<summary>Raw HTML'
check "mermaid loaded for scripts: [mermaid]"  has /_example/features.md '/_shared/vendor/mermaid.min.js'
check "style: paper switches stylesheet"       has /_example/paper.md '/_shared/paper.css'
check "frontmatter title becomes the heading"  has /_example/paper.md '<h1>Paper style</h1>'
check "leading --- rule is not frontmatter"    has /_smoke/docs/rule.md '<hr>'
check ".html is served as-is"                  bash -c "diff <(curl -s '$BASE/_example/showcase.html') '$ROOT/sites/_example/showcase.html'"
check "relative image is served"               ctype /_example/img/lantern.svg image/svg+xml
check "dir without README is listed"           has /_example/notes/ 'first.md'
check "dir without slash redirects"            status /_example 308
check "missing page is 404"                    status /_example/nope.md 404
check "dotfile is 404"                         status /_example/.not-served 404
check "encoded dotfile is 404"                 status /_example/%2enot-served 404
check "listing hides dotfiles"                 lacks /_example/ '.not-served'
check ".git/config is 404"                     status /_smoke/.git/config 404
check ".env is 404"                            status /_smoke/.env 404
check "node_modules is 404"                    status /_smoke/node_modules/x/index.js 404
check "__pycache__ is 404"                     status /_smoke/__pycache__/m.pyc 404
check "symlinked repo README renders"          has /_smoke/ '<h1 id="smoke-repo">'
check "shared assets are served"               ctype /_shared/style.css text/css
check "vendored mermaid is served"             status /_shared/vendor/mermaid.min.js 200
check "app route proxies"                      has /_example-app/ 'X-Forwarded-Prefix: /_example-app'
check "app sub-path proxies"                   has /_example-app/api/time '"now"'
check "app without slash redirects"            status /_example-app 308

echo "$pass passed, $failed failed ($BASE)"
((failed == 0))
