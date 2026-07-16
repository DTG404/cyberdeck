#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd "$(dirname "$0")/.." && pwd)
installer="$repo_dir/install/systemd.sh"
server="$repo_dir/server/server.py"
tui="$repo_dir/tui/tui.py"

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

grep -q 'EnvironmentFile=.*/config/server.conf' "$installer" ||
  fail 'systemd unit must load the token from a protected environment file'

if grep -q 'Environment=CYBERDECK_AUTH_TOKEN=' "$installer"; then
  fail 'systemd unit must not embed the token'
fi

grep -q '^CYBERDECK_AUTH_TOKEN=' "$installer" ||
  fail 'protected configuration must use the server variable name'

if grep -Eq 'Generated auth token:|echo[^#]*\$AUTH_TOKEN' "$installer"; then
  fail 'installer must never print the generated token'
fi

grep -q 'if not AUTH_TOKEN:' "$server" ||
  fail 'server must fail closed when authentication is not configured'

grep -q 'broadcast_task.cancel()' "$server" ||
  fail 'server must cancel its broadcaster during graceful shutdown'

grep -q 'os.environ.get("CYBERDECK_AUTH_TOKEN"' "$tui" ||
  fail 'TUI must load the protected token from its environment'

grep -q 'json.dumps({"token": AUTH_TOKEN})' "$tui" ||
  fail 'TUI must authenticate with the configured token'

printf 'Cyberdeck server security checks passed.\n'
