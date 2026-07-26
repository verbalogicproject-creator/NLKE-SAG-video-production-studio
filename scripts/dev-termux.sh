#!/data/data/com.termux/files/usr/bin/sh
set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RUN_DIR="$REPO_DIR/.termux-run"
PG_DIR="$RUN_DIR/postgres"
mkdir -p "$RUN_DIR"

if [ -f "$REPO_DIR/.env.local" ]; then
  set -a
  . "$REPO_DIR/.env.local"
  set +a
fi

: "${DATABASE_URL:=postgresql://localhost:5432/verbalogix_chamber}"
: "${SAG_VIDEO_SERVICE_TOKEN:=local-chamber-service}"
: "${SAG_ENGINE_URL:=http://127.0.0.1:8080}"
: "${VERBALOGIX_LOCAL_DEV:=1}"
: "${SAG_REPOSITORY_BACKEND:=postgres}"
: "${SAG_STORAGE_BACKEND:=filesystem}"
: "${SAG_VIDEO_STORAGE_ROOT:=$REPO_DIR/.sag-video/storage}"
export DATABASE_URL SAG_VIDEO_SERVICE_TOKEN SAG_ENGINE_URL VERBALOGIX_LOCAL_DEV
export SAG_REPOSITORY_BACKEND SAG_STORAGE_BACKEND SAG_VIDEO_STORAGE_ROOT

sh "$REPO_DIR/scripts/termux-preflight.sh"

if [ ! -f "$PG_DIR/PG_VERSION" ]; then
  initdb -D "$PG_DIR" --auth=trust >/dev/null
fi
if ! pg_ctl -D "$PG_DIR" status >/dev/null 2>&1; then
  pg_ctl -D "$PG_DIR" -l "$RUN_DIR/postgres.log" start >/dev/null
fi
createdb verbalogix_chamber 2>/dev/null || true

cd "$REPO_DIR"
pnpm db:generate
pnpm db:deploy

cd "$REPO_DIR/services/sag-engine"
PYTHONPATH=src uvicorn sag_video.observer_app:app --host 127.0.0.1 --port 8082 >"$RUN_DIR/observer.log" 2>&1 & echo $! >"$RUN_DIR/observer.pid"
SAG_VIDEO_OBSERVER_URL=http://127.0.0.1:8082 PYTHONPATH=src uvicorn sag_video.app:app --host 127.0.0.1 --port 8080 >"$RUN_DIR/engine.log" 2>&1 & echo $! >"$RUN_DIR/engine.pid"

cd "$REPO_DIR"
pnpm --filter @verbalogix/web dev >"$RUN_DIR/web.log" 2>&1 & echo $! >"$RUN_DIR/web.pid"

echo "Chamber starting: http://127.0.0.1:3000/dashboard"
echo "Logs and PID files: $RUN_DIR"
