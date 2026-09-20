# syntax=docker/dockerfile:1
FROM python:3.12.14-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
RUN pip install --no-cache-dir uv==0.11.33
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-default-groups --no-install-project

FROM python:3.12.14-slim AS runtime
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=config.settings.production
WORKDIR /app
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser
COPY --from=builder /app/.venv /app/.venv
COPY --chown=appuser:appuser manage.py ./
COPY --chown=appuser:appuser config ./config
COPY --chown=appuser:appuser apps ./apps
USER appuser
EXPOSE 8000
STOPSIGNAL SIGTERM
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
