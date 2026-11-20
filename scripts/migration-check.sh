#!/usr/bin/env bash
# Migration evidence: upgrade head -> downgrade base -> upgrade head -> check.
#
#   DATABASE_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/DB_NAME' \
#     ./scripts/migration-check.sh
#
# WARNING: this drops the three delivery tables on downgrade. Point it at a
# dedicated test database, never at shared data.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is required, e.g. postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/DB_NAME" >&2
  exit 2
fi

echo "== alembic upgrade head =="
.venv/bin/alembic upgrade head
echo "== alembic downgrade base =="
.venv/bin/alembic downgrade base
echo "== alembic upgrade head =="
.venv/bin/alembic upgrade head
echo "== alembic check =="
.venv/bin/alembic check
echo "== alembic current =="
.venv/bin/alembic current
