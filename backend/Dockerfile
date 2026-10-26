FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    poppler-utils \
    pandoc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY backend/pyproject.toml ./pyproject.toml
RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir -e .[dev] 2>&1 | tail -5

# Copy application code
COPY backend/app/ ./app/
COPY backend/.env ./app/.env

# Create data directories
RUN mkdir -p /data/kuzudb /data/wiki /data/raw_vault /config/domain_schemas && \
    mkdir -p /quarantine/slop

# Copy domain schemas
COPY --from=busybox:latest /dev/null /config/domain_schemas/.gitkeep

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]