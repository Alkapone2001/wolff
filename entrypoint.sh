#!/bin/sh
set -e

echo "Waiting for database to be ready..."
./wait-for-it.sh db:5432 --timeout=60 --strict -- echo "Database is up!"

echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting FastAPI server..."
exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
