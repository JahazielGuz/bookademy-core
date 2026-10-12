# syntax=docker/dockerfile:1

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Manifests first. This layer is rebuilt only when dependencies change, not on every
# code edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

# Static files are collected at build time so the running container needs no build
# tools and no write access to its own filesystem. settings.py reads DATABASE_URL at
# import, so collectstatic is given a placeholder it never connects to.
RUN SECRET_KEY=build-only DATABASE_URL=postgres://u:p@127.0.0.1:5432/db \
    uv run python manage.py collectstatic --noinput

FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=build /app /app

RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8000
# Overridden per process group in fly.toml; this is what `docker run` gets.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
