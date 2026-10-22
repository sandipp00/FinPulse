# Build context is the repository root (the API imports the `src` package too).
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Run as an unprivileged user; /app/data is the only place it writes.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/data \
    && chown -R app:app /app

WORKDIR /app

COPY requirements-api.txt .
RUN pip install -r requirements-api.txt


# ---- one-off job image: adds the market-data downloaders -----------------------
FROM base AS seed
COPY requirements-data.txt .
RUN pip install -r requirements-data.txt
COPY --chown=app:app src ./src
USER app
CMD ["sh", "-c", "python -m src.data.stock_data && python -m src.data.crypto_data && python -m src.data.build_database"]


# ---- the API server ------------------------------------------------------------
FROM base AS runtime
COPY --chown=app:app backend ./backend
COPY --chown=app:app src ./src
USER app

ENV DATABASE_PATH=/app/data/finpulse.db
VOLUME ["/app/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

# One worker on purpose: the live feed, WebSocket hub and login rate limiter
# all live in this process's memory.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
