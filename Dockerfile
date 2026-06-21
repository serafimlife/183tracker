FROM python:3.12-slim

# Install uv from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first so this layer is cached on source-only changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application source
COPY app/ ./app/
COPY docker/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# Run as non-root
RUN groupadd --gid 1001 botuser \
    && useradd --uid 1001 --gid 1001 --no-create-home botuser \
    && chown -R botuser:botuser /app

USER botuser

ENTRYPOINT ["/app/entrypoint.sh"]
