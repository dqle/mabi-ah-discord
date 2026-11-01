#!/bin/sh
# ---------------------------------------------------------------------------
# Entry point for the mabi-ah-discord image.
#
# Runs a local PostgreSQL server and the Discord bot in one container:
#   1. initialize the data directory on first run (a fresh/empty volume is fine,
#      the bot creates its own table)
#   2. start postgres against the data directory, create the database if missing
#   3. wait for it to accept connections (SQL round-trip, not just a socket)
#   4. run the given command (the bot) so SIGTERM from `docker stop` / a Pod
#      deletion reaches it, and the database is checkpointed and stopped cleanly
#
# Everything runs as the single unprivileged `app` user (uid 10001), which is a
# requirement for the helm Pod's runAsNonRoot security context.
# ---------------------------------------------------------------------------
set -eu

PGDATA="${PGDATA:-/data/pgdata}"
PG_PORT="${PG_PORT:-5432}"
PG_USER="${PG_USER:-mabi_ah}"
PG_DATABASE="${PG_DATABASE:-mabi_ah}"
PG_BIND_IP="${PG_BIND_IP:-127.0.0.1}"
PG_SOCKET_DIR="${PG_SOCKET_DIR:-/tmp}"
PG_LOG_DIR="${PG_LOG_DIR:-/var/log/postgresql}"
PG_SHARED_BUFFERS="${PG_SHARED_BUFFERS:-64MB}"
PG_WORK_MEM="${PG_WORK_MEM:-4MB}"

log() { echo "[entrypoint] $*"; }

# First run on an empty volume: initdb. A data directory without PG_VERSION is
# not initialized (or is the debris of an interrupted initdb), so it is safe to
# (re)run initdb in that case.
init_db() {
    mkdir -p "$PGDATA" "$PG_LOG_DIR"

    if [ -f "$PGDATA/PG_VERSION" ]; then
        log "data directory $PGDATA is already initialized"
        return
    fi

    log "initializing a new database in $PGDATA"
    # trust auth: the server listens on the loopback interface only and the bot
    # is its only client. See README for locking it down for a real deployment.
    initdb -D "$PGDATA" \
        --username "$PG_USER" \
        --encoding UTF8 \
        --locale C.UTF-8 \
        --auth-local trust \
        --auth-host trust \
        --no-sync >/dev/null
}

start_postgres() {
    # Loopback only, tiny shared_buffers so the database and the bot fit in the
    # memory limit, and the unix socket in /tmp (this image has no writable
    # /var/run/postgresql).
    pg_ctl \
        -D "$PGDATA" \
        -l "$PG_LOG_DIR/postgres.log" \
        -o "-p $PG_PORT -c listen_addresses=$PG_BIND_IP -c unix_socket_directories=$PG_SOCKET_DIR -c shared_buffers=$PG_SHARED_BUFFERS -c work_mem=$PG_WORK_MEM -c maintenance_work_mem=32MB -c max_connections=20" \
        -w -t 60 start >/dev/null
    log "postgres is up on $PG_BIND_IP:$PG_PORT"
}

# The database initdb created is owned by $PG_USER; make sure the one the bot
# connects to exists (idempotent, and it covers a volume initialized by hand).
ensure_database() {
    if ! psql -h "$PG_BIND_IP" -p "$PG_PORT" -U "$PG_USER" -d postgres -tAc \
            "SELECT 1 FROM pg_database WHERE datname = '$PG_DATABASE'" | grep -q 1
    then
        log "creating database $PG_DATABASE"
        createdb -h "$PG_BIND_IP" -p "$PG_PORT" -U "$PG_USER" -O "$PG_USER" "$PG_DATABASE"
    fi
}

# One query through the real driver: proves the server accepts connections and
# the bot's database is there.
ping_postgres() {
    python3 - "$PG_BIND_IP" "$PG_PORT" "$PG_DATABASE" <<'PY'
import sys, psycopg
host, port, db = sys.argv[1], int(sys.argv[2]), sys.argv[3]
with psycopg.connect(
    host=host, port=port, dbname=db, user="mabi_ah",
    connect_timeout=5,
) as conn:
    conn.execute("SELECT 1").fetchone()
PY
}

wait_for_postgres() {
    i=0
    until ping_postgres >/dev/null 2>&1; do
        i=$((i + 1))
        if [ "$i" -gt 60 ]; then
            log "postgres did not become ready within 60s"
            tail -n 40 "$PG_LOG_DIR/postgres.log" 2>/dev/null || true
            exit 1
        fi
        sleep 1
    done
    log "database is ready"
}

stop_postgres() {
    # SIGTERM to the postmaster is PostgreSQL's "fast shutdown": it rolls back
    # open transactions, runs a shutdown checkpoint and exits. Signal-based
    # because pg_ctl would need the unix socket to be reachable from here.
    if [ -f "$PGDATA/postmaster.pid" ]; then
        pid="$(head -n 1 "$PGDATA/postmaster.pid")"
        if kill -TERM "$pid" 2>/dev/null; then
            log "waiting for postgres (pid $pid) to shut down"
            i=0
            while kill -0 "$pid" 2>/dev/null && [ "$i" -lt 30 ]; do
                sleep 1
                i=$((i + 1))
            done
            if kill -0 "$pid" 2>/dev/null; then
                log "postgres did not exit within 30s"
            fi
        fi
    fi
}

init_db
start_postgres
ensure_database
wait_for_postgres

# Run the bot as a child (not exec) so this shell stays PID 1: signals from
# `docker stop` / a pod deletion land here, get forwarded to the bot so it can
# close its Discord connection, and only then is postgres shut down gracefully.
# That order matters for a mounted /data: postgres is never killed mid-write.
log "starting: $*"
"$@" &
bot_pid=$!

shutdown() {
    log "stopping bot, then database"
    kill -TERM "$bot_pid" 2>/dev/null || true
    wait "$bot_pid" 2>/dev/null || true
    stop_postgres
    exit 0
}
trap shutdown INT TERM

status=0
wait "$bot_pid" || status=$?
stop_postgres
exit "$status"
