#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://zurios.vercel.app}"
BASE_URL="${BASE_URL%/}"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

fetch_status() {
  local path="$1"
  curl --silent --show-error --output /dev/null --write-out '%{http_code}' "$BASE_URL$path"
}

fetch_type() {
  local path="$1"
  curl --silent --show-error --output /dev/null --write-out '%{content_type}' "$BASE_URL$path"
}

root_html="$(curl --fail --silent --show-error "$BASE_URL/")" || fail "Zuri OS root is unavailable"
grep -q '<title>Zuri OS</title>' <<<"$root_html" || fail "root route no longer serves Zuri OS"
pass "Zuri OS root remains intact"

app_html="$(curl --fail --silent --show-error "$BASE_URL/odeistudio")" || fail "ODEI route is unavailable"
grep -q '<title>ODEI Studio</title>' <<<"$app_html" || fail "ODEI route does not serve ODEI Studio"
js_path="$(sed -n 's/.*src="\([^"]*\.js\)".*/\1/p' <<<"$app_html" | head -n 1)"
css_path="$(sed -n 's/.*href="\([^"]*\.css\)".*/\1/p' <<<"$app_html" | head -n 1)"
[[ -n "$js_path" ]] || fail "HTML does not reference a JavaScript module"
[[ -n "$css_path" ]] || fail "HTML does not reference a stylesheet"
pass "ODEI HTML and asset references are present"

js_status="$(fetch_status "$js_path")"
js_type="$(fetch_type "$js_path")"
[[ "$js_status" == "200" ]] || fail "JavaScript returned HTTP $js_status"
[[ "$js_type" == application/javascript* || "$js_type" == text/javascript* ]] || fail "JavaScript has unexpected Content-Type: $js_type"
pass "JavaScript module returns 200 with JavaScript MIME type"

css_status="$(fetch_status "$css_path")"
css_type="$(fetch_type "$css_path")"
[[ "$css_status" == "200" ]] || fail "CSS returned HTTP $css_status"
[[ "$css_type" == text/css* ]] || fail "Stylesheet has unexpected Content-Type: $css_type"
pass "Stylesheet returns 200 with text/css"

nested_status="$(fetch_status "/odeistudio/nexus")"
[[ "$nested_status" == "200" ]] || fail "Nested SPA route returned HTTP $nested_status"
pass "Nested SPA route resolves"

missing_status="$(fetch_status "/odeistudio/assets/odei-smoke-missing-${GITHUB_RUN_ID:-local}.js")"
[[ "$missing_status" == "404" ]] || fail "Missing JavaScript asset returned HTTP $missing_status instead of 404"
pass "Missing assets are not rewritten to HTML"

api_status="$(fetch_status "/odeistudio/api/v1/health/live")"
api_type="$(fetch_type "/odeistudio/api/v1/health/live")"
if [[ "$api_status" == "404" ]]; then
  [[ "$api_type" != text/html* ]] || fail "Missing API route returned HTML"
  pass "API route fails closed (404) until dedicated ODEI API is deployed"
elif [[ "$api_status" == "200" || "$api_status" == "503" ]]; then
  [[ "$api_type" == application/json* ]] || fail "API health route returned non-JSON Content-Type: $api_type"
  pass "API health route responds with JSON (HTTP $api_status)"
else
  fail "API health route returned unexpected HTTP $api_status"
fi

echo "Production smoke checks passed for $BASE_URL"
