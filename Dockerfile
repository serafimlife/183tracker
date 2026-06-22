FROM python:3.12-slim

# Pin uv to an explicit version. To upgrade: bump the tag and update the digest.
# Get the current digest with: docker buildx imagetools inspect ghcr.io/astral-sh/uv:0.7.13
COPY --from=ghcr.io/astral-sh/uv:0.7.13 /uv /usr/local/bin/uv

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
    && useradd --uid 1001 --gid 1001 --create-home botuser \
    && chown -R botuser:botuser /app

USER botuser

ENTRYPOINT ["/app/entrypoint.sh"]
