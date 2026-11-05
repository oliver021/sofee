#!/usr/bin/env bash
#
# Sofee quick preview: one command to run the whole app on your machine.
#
#   scripts/quick-preview.sh                 # app + demo data, no model yet (replays and UI only)
#   scripts/quick-preview.sh --local-llm     # also download and run a local model + embeddings
#   scripts/quick-preview.sh stop            # stop everything (add --purge to delete the data too)
#
# What it does: starts its own PostgreSQL in Docker (container `sofee-preview-db`, so it never
# touches your development database), builds apps/web and apps/admin, applies the migrations,
# seeds the demo (users, 14 fictional team documents, agent profiles, RAG index) and serves
# everything from one process: the app at /, the admin panel at /admin, the API at /api/v1.
#
# Models, pick one:
#   * --local-llm                     llama.cpp + Qwen3-8B (chat) + Qwen3-Embedding-0.6B (RAG).
#                                     About 5.5 GB of downloads, asked before starting.
#   * SOFEE_DEMO_PROVIDER_KIND=...    a hosted provider (see "Demo end to end" in the README).
#     SOFEE_DEMO_API_KEY=...          Keys are read from your shell, stored encrypted in the
#     SOFEE_DEMO_MAIN_MODEL=...       preview database and never written to the repository.
#   Optional: SOFEE_DEMO_TAVILY_API_KEY (web search) and, to turn on RAG with a hosted
#   embeddings endpoint, SOFEE_EMBEDDINGS_BASE_URL + SOFEE_EMBEDDINGS_MODEL
#   (+ SOFEE_EMBEDDINGS_API_KEY).
#
# Settings (environment): SOFEE_PORT=8000  SOFEE_PG_PORT=5439  SOFEE_LLM_PORT=8081
#   SOFEE_EMBED_PORT=8082  SOFEE_LLAMA_DIR=~/.local/share/sofee-llama
#
# Requires: Docker, Node.js 20+, npm and uv (https://docs.astral.sh/uv/). Linux or macOS.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$ROOT/.preview"
API_DIR="$ROOT/apps/api"

PORT="${SOFEE_PORT:-8000}"
PG_PORT="${SOFEE_PG_PORT:-5439}"
LLM_PORT="${SOFEE_LLM_PORT:-8081}"
EMBED_PORT="${SOFEE_EMBED_PORT:-8082}"
LLAMA_DIR="${SOFEE_LLAMA_DIR:-$HOME/.local/share/sofee-llama}"
DB_CONTAINER="sofee-preview-db"
DB_VOLUME="sofee_preview_pgdata"

# llama.cpp release pinned so the download is reproducible, and the models it serves.
LLAMA_TAG="b12129"
CHAT_MODEL_FILE="Qwen3-8B-Q4_K_M.gguf"
CHAT_MODEL_URL="https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/main/$CHAT_MODEL_FILE"
EMBED_MODEL_FILE="Qwen3-Embedding-0.6B-Q8_0.gguf"
EMBED_MODEL_URL="https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF/resolve/main/$EMBED_MODEL_FILE"

LOCAL_LLM=0
BUILD=1
ASSUME_YES=0
COMMAND="start"
PURGE=0

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }
die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '3,28p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  cat <<'EOF'

Options:
  --local-llm   download (if needed) and run a local model and embeddings
  --no-build    reuse the existing apps/web/dist and apps/admin/dist
  --yes         do not ask before downloading models
  --purge       with `stop`: also delete the preview database and settings
  -h, --help    show this help
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    start|stop) COMMAND="$1" ;;
    --local-llm) LOCAL_LLM=1 ;;
    --no-build) BUILD=0 ;;
    --yes|-y) ASSUME_YES=1 ;;
    --purge) PURGE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown argument: $1" ;;
  esac
  shift
done

stop_pidfile() {
  local file="$1"
  [ -f "$file" ] || return 0
  local pid
  pid="$(cat "$file")"
  if kill -0 "$pid" 2>/dev/null; then kill "$pid" 2>/dev/null || true; fi
  rm -f "$file"
}

stop_all() {
  say "Stopping Sofee preview"
  stop_pidfile "$STATE/api.pid"
  stop_pidfile "$STATE/llm.pid"
  stop_pidfile "$STATE/embed.pid"
  if command -v docker >/dev/null 2>&1; then
    docker stop "$DB_CONTAINER" >/dev/null 2>&1 || true
    if [ "$PURGE" = 1 ]; then
      docker rm "$DB_CONTAINER" >/dev/null 2>&1 || true
      docker volume rm "$DB_VOLUME" >/dev/null 2>&1 || true
    fi
  fi
  if [ "$PURGE" = 1 ]; then rm -rf "$STATE"; fi
  say "Done."
}

if [ "$COMMAND" = "stop" ]; then stop_all; exit 0; fi

# --- prerequisites -------------------------------------------------------------------------

need() { command -v "$1" >/dev/null 2>&1 || die "$1 is required. $2"; }
need docker "Install Docker: https://docs.docker.com/get-docker/"
need node "Install Node.js 20 or newer: https://nodejs.org/"
need npm "It ships with Node.js."
need uv "Install uv: https://docs.astral.sh/uv/getting-started/installation/"
need curl "Install curl."
docker info >/dev/null 2>&1 || die "Docker is installed but not running."
[ "$(node -p 'process.versions.node.split(".")[0]')" -ge 20 ] || die "Node.js 20 or newer is required."

for port in "$PORT" "$PG_PORT"; do
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    # Our own database container may already be the one listening: that is fine.
    if [ "$port" = "$PG_PORT" ] && docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER"; then continue; fi
    die "Port $port is already in use. Set SOFEE_PORT / SOFEE_PG_PORT to free ports, or run: $0 stop"
  fi
done

mkdir -p "$STATE"
cleanup() {
  stop_pidfile "$STATE/api.pid"
  stop_pidfile "$STATE/llm.pid"
  stop_pidfile "$STATE/embed.pid"
}
trap 'cleanup; exit 0' INT TERM

# --- database ------------------------------------------------------------------------------

say "Starting PostgreSQL ($DB_CONTAINER on port $PG_PORT)"
if docker ps -a --format '{{.Names}}' | grep -qx "$DB_CONTAINER"; then
  docker start "$DB_CONTAINER" >/dev/null
else
  docker run -d --name "$DB_CONTAINER" \
    -e POSTGRES_USER=sofee -e POSTGRES_PASSWORD=sofee -e POSTGRES_DB=sofee_preview \
    -p "127.0.0.1:$PG_PORT:5432" -v "$DB_VOLUME:/var/lib/postgresql/data" \
    postgres:17-alpine >/dev/null
fi
for _ in $(seq 1 60); do
  if docker exec "$DB_CONTAINER" pg_isready -U sofee -d sofee_preview >/dev/null 2>&1; then break; fi
  sleep 1
done
docker exec "$DB_CONTAINER" pg_isready -U sofee -d sofee_preview >/dev/null 2>&1 || die "PostgreSQL did not become ready."

# --- dependencies and builds ---------------------------------------------------------------

say "Installing dependencies"
(cd "$ROOT" && npm install --no-audit --no-fund --loglevel=error)
(cd "$API_DIR" && uv sync --quiet)

if [ "$BUILD" = 1 ] || [ ! -d "$ROOT/apps/web/dist" ] || [ ! -d "$ROOT/apps/admin/dist" ]; then
  say "Building the app and the admin panel"
  (cd "$ROOT" && npm run build --silent && npm run build:admin --silent)
fi

# --- secrets (generated once, kept in .preview/env, gitignored) ----------------------------

if [ ! -f "$STATE/env" ]; then
  say "Generating local secrets in .preview/env"
  {
    echo "SECRET_ENCRYPTION_KEY=$(cd "$API_DIR" && uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
    echo "CSRF_SECRET=$(cd "$API_DIR" && uv run python -c 'import secrets; print(secrets.token_hex(32))')"
    echo "SOFEE_DEMO_ADMIN_PASSWORD=$(cd "$API_DIR" && uv run python -c 'import secrets; print(secrets.token_urlsafe(12))')"
    echo "SOFEE_DEMO_USER_PASSWORD=$(cd "$API_DIR" && uv run python -c 'import secrets; print(secrets.token_urlsafe(12))')"
  } > "$STATE/env"
  chmod 600 "$STATE/env"
fi
set -a
# shellcheck disable=SC1091
. "$STATE/env"
set +a

# --- local models (optional) ---------------------------------------------------------------

LLAMA_SERVER=""
download() { # url, destination
  say "Downloading $(basename "$2")"
  curl -fL --progress-bar -C - -o "$2.part" "$1" && mv "$2.part" "$2"
}

ensure_llama_server() {
  if command -v llama-server >/dev/null 2>&1; then LLAMA_SERVER="$(command -v llama-server)"; return; fi
  if [ -x "$LLAMA_DIR/bin/llama-server" ]; then LLAMA_SERVER="$LLAMA_DIR/bin/llama-server"; return; fi
  local asset=""
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) asset="llama-$LLAMA_TAG-bin-ubuntu-vulkan-x64.tar.gz" ;;
    Darwin-arm64) asset="llama-$LLAMA_TAG-bin-macos-arm64.tar.gz" ;;
    *) die "No prebuilt llama.cpp for this system. Install llama-server (https://github.com/ggml-org/llama.cpp) and run again." ;;
  esac
  mkdir -p "$LLAMA_DIR/bin"
  download "https://github.com/ggml-org/llama.cpp/releases/download/$LLAMA_TAG/$asset" "$LLAMA_DIR/llama.tar.gz"
  tar -xzf "$LLAMA_DIR/llama.tar.gz" -C "$LLAMA_DIR/bin" --strip-components=1
  rm -f "$LLAMA_DIR/llama.tar.gz"
  LLAMA_SERVER="$LLAMA_DIR/bin/llama-server"
  [ -x "$LLAMA_SERVER" ] || die "llama-server was not found in the downloaded archive."
}

wait_for_http() { # url, label
  for _ in $(seq 1 180); do
    if curl -fsS -m 2 "$1" >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  die "$2 did not become ready ($1)."
}

start_local_models() {
  mkdir -p "$LLAMA_DIR/models"
  local missing=()
  [ -f "$LLAMA_DIR/models/$CHAT_MODEL_FILE" ] || missing+=("$CHAT_MODEL_FILE (4.8 GB)")
  [ -f "$LLAMA_DIR/models/$EMBED_MODEL_FILE" ] || missing+=("$EMBED_MODEL_FILE (0.6 GB)")
  if [ ${#missing[@]} -gt 0 ]; then
    say "The local models need to be downloaded to $LLAMA_DIR/models:"
    printf '      - %s\n' "${missing[@]}"
    if [ "$ASSUME_YES" != 1 ]; then
      [ -t 0 ] || die "Not a terminal: run again with --yes to download without asking."
      read -r -p "Download now? [y/N] " answer
      case "$answer" in y|Y|yes|YES) ;; *) die "Cancelled. Run again without --local-llm to start without a model." ;; esac
    fi
    [ -f "$LLAMA_DIR/models/$CHAT_MODEL_FILE" ] || download "$CHAT_MODEL_URL" "$LLAMA_DIR/models/$CHAT_MODEL_FILE"
    [ -f "$LLAMA_DIR/models/$EMBED_MODEL_FILE" ] || download "$EMBED_MODEL_URL" "$LLAMA_DIR/models/$EMBED_MODEL_FILE"
  fi
  ensure_llama_server

  local lib_path="$(dirname "$LLAMA_SERVER")"
  say "Starting the chat model on port $LLM_PORT (first load takes a moment)"
  LD_LIBRARY_PATH="$lib_path${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" nohup "$LLAMA_SERVER" \
    -m "$LLAMA_DIR/models/$CHAT_MODEL_FILE" --host 127.0.0.1 --port "$LLM_PORT" \
    --jinja -ngl 99 -c 16384 --parallel 1 --alias qwen3-8b-local \
    --chat-template-kwargs '{"enable_thinking": false}' \
    --temp 0.7 --top-p 0.8 --top-k 20 --min-p 0 --presence-penalty 1.0 \
    > "$STATE/llm.log" 2>&1 &
  echo $! > "$STATE/llm.pid"

  say "Starting the embeddings model on port $EMBED_PORT"
  LD_LIBRARY_PATH="$lib_path${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" nohup "$LLAMA_SERVER" \
    -m "$LLAMA_DIR/models/$EMBED_MODEL_FILE" --host 127.0.0.1 --port "$EMBED_PORT" \
    --embeddings --pooling last -ngl 0 -c 4096 --alias qwen3-embedding-0.6b \
    > "$STATE/embed.log" 2>&1 &
  echo $! > "$STATE/embed.pid"

  wait_for_http "http://127.0.0.1:$LLM_PORT/health" "The chat model"
  wait_for_http "http://127.0.0.1:$EMBED_PORT/health" "The embeddings model"

  export SOFEE_DEMO_PROVIDER_KIND=openai_compatible
  export SOFEE_DEMO_BASE_URL="http://127.0.0.1:$LLM_PORT/v1"
  export SOFEE_DEMO_API_KEY=local-llama
  export SOFEE_DEMO_MAIN_MODEL=qwen3-8b-local
  export SOFEE_DEMO_CONTEXT_WINDOW=16384
  export EMBEDDINGS_BASE_URL="http://127.0.0.1:$EMBED_PORT/v1"
  export EMBEDDINGS_MODEL=qwen3-embedding-0.6b
  # Qwen3-Embedding wants an instruction in front of the *question* (never the documents).
  export EMBEDDINGS_QUERY_PREFIX='Instruct: Given a question from a new team member, retrieve the passages of the team documentation that answer it\nQuery: '
}

if [ "$LOCAL_LLM" = 1 ]; then
  start_local_models
elif [ -n "${SOFEE_EMBEDDINGS_BASE_URL:-}" ] && [ -n "${SOFEE_EMBEDDINGS_MODEL:-}" ]; then
  export EMBEDDINGS_BASE_URL="$SOFEE_EMBEDDINGS_BASE_URL"
  export EMBEDDINGS_MODEL="$SOFEE_EMBEDDINGS_MODEL"
  export EMBEDDINGS_API_KEY="${SOFEE_EMBEDDINGS_API_KEY:-}"
  export EMBEDDINGS_QUERY_PREFIX="${SOFEE_EMBEDDINGS_QUERY_PREFIX:-}"
fi

# --- schema and demo data ------------------------------------------------------------------

export DATABASE_URL="postgresql+asyncpg://sofee:sofee@127.0.0.1:$PG_PORT/sofee_preview"
export STORAGE_LOCAL_DIR="$STATE/storage"
export SESSION_COOKIE_SECURE=false

say "Applying migrations and seeding the demo"
(cd "$API_DIR" \
  && uv run alembic upgrade head 2>&1 | tail -n 1 \
  && uv run python -m app.cli setup-agent-storage \
  && uv run python -m app.cli seed-demo)

# --- run -----------------------------------------------------------------------------------

say "Starting Sofee on port $PORT"
(cd "$API_DIR" && exec uv run uvicorn app.main:app --host 127.0.0.1 --port "$PORT" > "$STATE/api.log" 2>&1) &
echo $! > "$STATE/api.pid"
wait_for_http "http://127.0.0.1:$PORT/healthz" "The API"

cat <<EOF

  Sofee quick preview is running.

    App    http://localhost:$PORT/
    Admin  http://localhost:$PORT/admin/

    Demo user   usuario@sofee.demo   $SOFEE_DEMO_USER_PASSWORD
    Admin user  admin@sofee.demo     $SOFEE_DEMO_ADMIN_PASSWORD
    (or create your own account on the sign-in screen)

  Press Ctrl+C to stop the app and the models. Run "$0 stop" to also stop the database.
  Logs: .preview/api.log  .preview/llm.log  .preview/embed.log

EOF
if [ "$LOCAL_LLM" != 1 ] && [ -z "${SOFEE_DEMO_PROVIDER_KIND:-}" ]; then
  warn "No model configured: the assistant cannot answer live. Run with --local-llm, or set SOFEE_DEMO_PROVIDER_KIND and SOFEE_DEMO_API_KEY."
fi

wait "$(cat "$STATE/api.pid")" 2>/dev/null || true
cleanup
