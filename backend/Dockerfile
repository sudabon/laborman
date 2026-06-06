FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /bin/
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

COPY backend ./backend

EXPOSE 8000
CMD ["sh", "-c", ".venv/bin/alembic -c backend/alembic.ini upgrade head && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend"]
