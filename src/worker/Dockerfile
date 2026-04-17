FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./

RUN uv sync --no-dev --frozen

COPY src/backend ./src/backend
COPY src/worker ./src/worker

ENV PYTHONPATH=/app

CMD ["uv", "run", "python", "-m", "src.worker.main"]
