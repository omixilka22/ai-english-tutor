#!/usr/bin/env bash
# Invoked over SSH with: bash -s -- /absolute/repository/path commit_sha
set -Eeuo pipefail
umask 077
repo=${1:?Repository path required}
sha=${2:?Commit SHA required}
[[ "$repo" = /* && "$sha" =~ ^[0-9a-f]{40}$ ]] || exit 2
cd "$repo"
exec 9>.git/deploy.lock
flock -n 9 || { echo "Another deployment is running"; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "Server checkout has local changes; deployment stopped"; exit 1; }
[[ -f .env ]] || { echo "Server .env missing"; exit 1; }
git fetch origin master
[[ "$(git rev-parse origin/master)" = "$sha" ]] || { echo "Commit superseded; skipping"; exit 0; }
[[ "$(git branch --show-current)" = master ]] || { echo "Server must be on master"; exit 1; }
git merge --ff-only "$sha"
dc() { docker compose -f compose.production.yml "$@"; }
dc config --quiet
# Build before stopping the running application.
dc build
dc up -d --wait postgres
mkdir -p backups
backup="backups/pre-deploy-$(date -u +%Y%m%dT%H%M%SZ)-${sha:0:12}.dump"
dc exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup.tmp"
test -s "$backup.tmp"
mv "$backup.tmp" "$backup"
dc stop bot gateway
# Failure stops deployment. Do not auto-downgrade a migrated database.
dc run --rm --no-deps migrate
dc up -d --no-deps --force-recreate --wait --wait-timeout 120 gateway
dc up -d --no-deps --force-recreate bot
dc up -d --no-deps caddy
dc exec -T caddy caddy reload --config /etc/caddy/Caddyfile
# Running is only a process-level smoke check; it is not a Telegram API test.
sleep 10
bot_id=$(dc ps -q bot)
test -n "$bot_id"
test "$(docker inspect --format '{{.State.Running}} {{.RestartCount}}' "$bot_id")" = "true 0"
dc exec -T gateway python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=5)"
echo "Deployed $sha. Database backup: $backup"
