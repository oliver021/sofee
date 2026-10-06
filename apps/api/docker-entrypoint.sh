#!/bin/sh
#
# Entrypoint de la imagen `sofee-api`. Comandos:
#
#   serve     (default)   arranca el proceso web (uvicorn). NUNCA toca la BD.
#   migrate               aplica `alembic upgrade head` y sale. Paso de release.
#
# Las migraciones se ejecutan en el job de release, una sola vez, y no en el
# arranque de las réplicas (si no, cada réplica las disputaría).

set -eu

cmd="${1:-serve}"
# shellcheck disable=SC2162
shift 2>/dev/null || true

case "$cmd" in
  serve)
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" "$@"
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  release)
    exec alembic upgrade head
    ;;
  *)
    exec "$cmd" "$@"
    ;;
esac