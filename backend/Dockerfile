FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# System dependencies for the document extraction paths (PDF / DOCX).
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libssl-dev \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# The package sources must be present *before* the editable install, otherwise
# the build backend cannot work out what to ship.
COPY backend/pyproject.toml ./pyproject.toml
COPY backend/README.md ./README.md
COPY backend/kuzuwiki/ ./kuzuwiki/

ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

# pip's build isolation installs the pinned build backend itself. Installing
# hatchling separately shadows it and breaks the editable metadata hook.
RUN pip install --no-cache-dir -e .

# Mount points for the compiled graph, the wiki vault and the raw archive.
RUN mkdir -p /data/kuzudb /data/wiki /data/raw_vault /quarantine/slop \
             /config/domain_schemas

# Domain packs (Layer 3 governance) are baked in so the container works even
# without the compose bind mount.
COPY config/domain_schemas/ /config/domain_schemas/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run as an unprivileged user. The entrypoint starts as root only to fix the
# ownership of the bind-mounted data volumes, then drops back to this user.
COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN useradd --create-home --uid 10001 kuzuwiki \
    && chown -R kuzuwiki:kuzuwiki /app /data /quarantine /config \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

CMD ["uvicorn", "kuzuwiki.main:app", "--host", "0.0.0.0", "--port", "8000"]
