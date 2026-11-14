FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src

# Output is written relative to /app, so mount divisions/, jurisdictions/,
# data/ and logs/ to keep results. Pass state codes as arguments, e.g.
#   docker run ... jurisdictions --state wa,tx
ENTRYPOINT ["python", "-m", "src.init_migration.main"]
