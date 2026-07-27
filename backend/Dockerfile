FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml .
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
RUN pip wheel --no-cache-dir --wheel-dir /wheels .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 appuser
COPY --from=builder /wheels /wheels
COPY --from=builder /build/migrations ./migrations
COPY --from=builder /build/alembic.ini ./alembic.ini
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
USER appuser
WORKDIR /app
EXPOSE 8000
CMD ["uvicorn", "screener.main:app", "--host", "0.0.0.0", "--port", "8000"]
