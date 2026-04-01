FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN : \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        libexpat1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /hls_vi

COPY ./ ./
RUN uv sync --frozen --group dev

CMD ["sh", "-c", "uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest -vv --doctest-modules"]
