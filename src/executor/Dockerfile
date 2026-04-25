FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY src/executor/pyproject.toml ./pyproject.toml

RUN uv pip install --system fastapi uvicorn pandas pyreadstat

COPY src/executor/ .

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
