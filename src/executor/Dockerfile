FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/default-java

RUN pip install --no-cache-dir uv

COPY src/executor/pyproject.toml ./pyproject.toml

RUN uv pip install --system fastapi uvicorn pandas pyreadstat pyspark

COPY src/executor/ .

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
