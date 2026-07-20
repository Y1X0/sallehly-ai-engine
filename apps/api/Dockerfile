FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml uv.lock* /app/
COPY apps/api /app/apps/api
COPY packages /app/packages

RUN pip install --no-cache-dir uv && \
    uv pip install --system -e ./apps/api -e ./packages/schemas

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
