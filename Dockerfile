FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN useradd --create-home --uid 1000 user
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev && chown -R user /app

USER user
ENV HOME=/home/user \
    PATH=/app/.venv/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface \
    ANKI_MCP_TRANSPORT=http \
    ANKI_MCP_HOST=0.0.0.0 \
    ANKI_MCP_PORT=7860

RUN python -c "import duckdb; duckdb.connect().execute('INSTALL fts')"

EXPOSE 7860
CMD ["anki-addons-mcp"]
