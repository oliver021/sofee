# syntax=docker/dockerfile:1
#
# Imagen de producción de apps/api. El build context es la raíz del monorepo
# porque la imagen sirve además el frontend apps/web en / y el panel admin
# (apps/admin) como estático en /admin (decisión 3: mismo dominio). Requiere
# haber construido ambos primero:
#
#   npm run build                  # -> genera apps/web/dist
#   npm run build:admin            # -> genera apps/admin/dist
#   docker build -t sofee-api -f apps/api/Dockerfile .
#
# Las migraciones de Alembic NO corren al arrancar el proceso web: son un paso de
# release aparte (ver docker-entrypoint.sh y docs/deployment.md).

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /build
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --no-dev --frozen

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/apps/.venv/bin:$PATH"
WORKDIR /apps

COPY --from=builder /build/.venv ./.venv

# uv crea el venv con la ruta absoluta del stage de build y el venv se ha
# reubicado en /apps/.venv: se reescriben los shebangs a esa ruta final.
RUN sed -i 's|^#!.*/bin/python[0-9.]*$|#!/apps/.venv/bin/python|' /apps/.venv/bin/* || true

COPY apps/api/app ./app
COPY apps/api/alembic ./alembic
COPY apps/api/alembic.ini ./alembic.ini
COPY apps/api/demo ./demo
COPY apps/api/docker-entrypoint.sh ./docker-entrypoint.sh
COPY apps/admin/dist ./admin_dist
COPY apps/web/dist ./web_dist

RUN chmod +x ./docker-entrypoint.sh

ENV ADMIN_DIST_DIR=/apps/admin_dist \
    WEB_DIST_DIR=/apps/web_dist

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["serve"]