FROM ghcr.io/astral-sh/uv:0.12.15 AS uv
FROM python:3.12-slim AS runtime
LABEL org.opencontainers.image.licenses="MIT"

COPY --from=uv /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PRZEPISNIK_DATA=/data \
    PRZEPISNIK_CONFIG=/app/docker/server.toml
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir /data && chown app:app /data
COPY docker/entrypoint.sh docker/server.toml /app/docker/
COPY docker/demo/placeholder.png /app/docker/placeholder.png
USER app
EXPOSE 8000
# Ready once the recipe API answers; Compose `up --wait` relies on this status.
HEALTHCHECK --interval=5s --timeout=4s --start-period=10s --retries=12 \
    CMD ["/app/.venv/bin/python", "-m", "przepisnik.web.health"]
ENTRYPOINT ["/bin/sh", "/app/docker/entrypoint.sh"]

# The demo is an explicit target; production builds do not contain its recipes.
FROM runtime AS demo
USER root
RUN mkdir /demo-data && chown app:app /demo-data
COPY docker/demo /app/docker/demo
ENV PRZEPISNIK_DATA=/demo-data \
    PRZEPISNIK_CONFIG=/app/docker/demo/server.toml
USER app
ENTRYPOINT ["/bin/sh", "/app/docker/demo/entrypoint.sh"]

# Keep the normal/default build suitable for an instance with its own data.
FROM runtime AS app
