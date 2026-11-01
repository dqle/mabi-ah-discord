#!/bin/sh
# ---------------------------------------------------------------------------
# Container healthcheck: ping the local PostgreSQL the same way the bot talks to
# it - a real query through the driver, not just a listening socket. Used by
# docker compose (healthcheck) and by the helm chart (liveness/readiness probes)
# so a container that lost its database is not reported as healthy while the bot
# keeps running.
# ---------------------------------------------------------------------------
set -eu

HOST="${PGHOST:-127.0.0.1}"
PORT="${PG_PORT:-5432}"
USER="${PG_USER:-mabi_ah}"
DB="${PG_DATABASE:-mabi_ah}"

python3 - "$HOST" "$PORT" "$DB" "$USER" <<'PY'
import sys, psycopg
host, port, db, user = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
with psycopg.connect(host=host, port=port, dbname=db, user=user, connect_timeout=5) as conn:
    conn.execute("SELECT 1").fetchone()
print("ok")
PY
