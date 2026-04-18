FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock README.md ./

# Install runtime deps only (no dev extras)
RUN uv sync --no-dev --frozen

# Copy source
COPY src/backend ./src/backend
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

ENV PYTHONPATH=/app

RUN chmod +x src/backend/entrypoint.sh

CMD ["sh", "src/backend/entrypoint.sh"]
