#!/bin/sh
set -eu
export PGPASSWORD="${POSTGRES_PASSWORD}"
HOST="${POSTGRES_HOST:-postgres}"
USER="${POSTGRES_USER:-zopro}"
DB="${POSTGRES_DB:-zopro}"

echo "waiting for postgres…"
i=0
until pg_isready -h "$HOST" -U "$USER" -d "$DB"; do
  i=$((i+1))
  if [ "$i" -gt 60 ]; then
    echo "postgres did not become ready"
    exit 1
  fi
  sleep 2
done

count="$(psql -h "$HOST" -U "$USER" -d "$DB" -tAc "SELECT COUNT(*) FROM sales.orders" 2>/dev/null || echo 0)"
count="$(echo "$count" | tr -d ' ')"
if [ -n "$count" ] && [ "$count" -gt 0 ] 2>/dev/null; then
  echo "already seeded ($count orders) — applying roles/helpers"
else
  echo "restoring /dump/wwi-postgres.dump"
  pg_restore -h "$HOST" -U "$USER" -d "$DB" --no-owner --no-acl /dump/wwi-postgres.dump
fi

psql -h "$HOST" -U "$USER" -d "$DB" -v ON_ERROR_STOP=1 -f /roles.sql
psql -h "$HOST" -U "$USER" -d "$DB" -v ON_ERROR_STOP=1 -f /after_restore.sql
echo "seed complete"
