# syntax=docker/dockerfile:1
# Earth Trend Detective API (FastAPI). Build context: the repo root.
#   docker build -f backend/Dockerfile -t etd-api .
# Secrets are runtime env only (OPENROUTER_API_KEY or LLM_API_KEY, NASA_TOKEN, APPEEARS_TOKEN).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.7.3 /uv /uvx /usr/local/bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/backend/.venv

# Layout mirrors the repo: the code resolves sites/ and .env from the repo root
# (Path(__file__).parents[...]), so /app is the "repo root" and /app/backend the project.
WORKDIR /app/backend

# Dependencies first (cached layer), exactly as locked; no dev group.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
COPY backend/catalog ./catalog
COPY backend/scripts ./scripts
COPY sites /app/sites
RUN uv sync --frozen --no-dev

# Non-root user. The data dirs exist in the image, owned by the user, so a fresh
# named volume mounted on them inherits that ownership.
RUN useradd --system --uid 10001 --home-dir /home/app --create-home app \
 && mkdir -p data/cache data/detective data/recordings \
 && chown -R app:app /app/backend/data

ENV PATH="/app/backend/.venv/bin:$PATH" \
    DETECTIVE_DB=/app/backend/data/detective/detective.sqlite \
    LANGSMITH_TRACING=false \
    LANGCHAIN_TRACING_V2=false

USER app
EXPOSE 8000
VOLUME ["/app/backend/data/cache", "/app/backend/data/detective"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
