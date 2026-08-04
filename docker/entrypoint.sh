#!/bin/bash
set -e

echo "=== Multicare HMS starting ==="

# Wait for Postgres to accept connections
if [ -n "$DB_HOST" ]; then
    echo "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT:-5432}..."
    until python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('${DB_HOST}', ${DB_PORT:-5432}))" 2>/dev/null; do
        echo "  Postgres not ready yet, sleeping..."
        sleep 1
    done
    echo "PostgreSQL is up."
fi

# Migrate
echo "Running database migrations..."
python manage.py migrate --noinput

# Collect static
# Collect static
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

# Bootstrap admin user and seed catalogs (idempotent)
echo "Running deploy bootstrap..."
python manage.py bootstrap_deploy || echo "Bootstrap encountered errors; continuing."

echo "=== Setup complete, handing off to CMD ==="

echo "=== Setup complete, handing off to CMD ==="
exec "$@"