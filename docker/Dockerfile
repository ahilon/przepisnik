FROM ghcr.io/astral-sh/uv:0.12.15 AS uv
FROM python:3.12-slim

COPY --from=uv /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir /demo-data && chown app:app /demo-data
COPY docker/demo /app/docker/demo
USER app
EXPOSE 8000
# Ready once the recipe API answers; Compose `up --wait` relies on this status.
HEALTHCHECK --interval=5s --timeout=4s --start-period=10s --retries=12 \
    CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/recipes', timeout=3).read()"]
ENTRYPOINT ["/bin/sh", "/app/docker/demo/entrypoint.sh"]
