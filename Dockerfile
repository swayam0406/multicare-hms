# ================================================================
# Multicare HMS — Multi-stage Docker build
# Base: Python 3.12 slim (Django 5.2 officially supported)
# ================================================================

# ---------- Stage 1: builder ----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps needed to build wheels (psycopg, Pillow etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install Python deps into a venv we can copy to the final stage
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install gunicorn whitenoise

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=multicare_hms.settings

# Runtime system deps only (no compilers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/*

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv

# Create non-root user
RUN groupadd -r hms && useradd -r -g hms hms

WORKDIR /app

# Copy project files
COPY --chown=hms:hms . /app/

# Ensure entrypoint is executable
RUN chmod +x /app/docker/entrypoint.sh

# Create writable dirs for the non-root user
RUN mkdir -p /app/staticfiles /app/media \
    && chown -R hms:hms /app/staticfiles /app/media

USER hms

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "multicare_hms.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "--error-logfile", "-"]