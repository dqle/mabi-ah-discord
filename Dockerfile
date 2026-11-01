# ---------------------------------------------------------------------------
# Stage 1: build a wheelhouse of the Python dependencies so the runtime image
# can install them offline and throw the toolchain away.
# ---------------------------------------------------------------------------
FROM python:3.12.4-slim AS build

WORKDIR /build
COPY requirements.txt .

# `pip wheel` downloads every wheel it resolves (direct + transitive deps), so
# the runtime install needs no compiler, no index and no build tools.
# psycopg[binary] carries its own libpq wheel: no libpq-dev, no pg_config.
RUN pip wheel --wheel-dir=/wheels -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: runtime image = Python + the bot + a local PostgreSQL server.
#
# The database ships inside this image (Debian bookworm's PostgreSQL 15), so
# `docker run`, docker compose and a single-replica helm Pod all get a fully
# local database: no cloud Postgres, no RDS, no sidecar. Data lives in
# /data/pgdata, which is a volume in compose/helm.
# ---------------------------------------------------------------------------
FROM python:3.12.4-slim

ARG PG_MAJOR=15

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PG_MAJOR=${PG_MAJOR} \
    PGDATA=/data/pgdata \
    PG_PORT=5432 \
    PG_USER=mabi_ah \
    PG_DATABASE=mabi_ah \
    PGHOST=127.0.0.1 \
    PG_LOG_DIR=/var/log/postgresql \
    PATH=/usr/lib/postgresql/${PG_MAJOR}/bin:${PATH} \
    POSTGRES_CONNECTION_STRING=postgresql://mabi_ah@127.0.0.1:5432/mabi_ah

# `postgresql-common` normally creates a default "15/main" cluster under
# /var/lib/postgresql during install. This image owns its own data directory
# (/data, a volume) and starts the server itself from the entrypoint, so the
# default cluster is switched off before the server package is installed
# (pg_conftool reports a boolean as "off").
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl ca-certificates; \
    apt-get install -y --no-install-recommends postgresql-common; \
    echo 'create_main_cluster = false' >> /etc/postgresql-common/createcluster.conf; \
    test "$(pg_conftool /etc/postgresql-common/createcluster.conf show -bs create_main_cluster)" = 'off'; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        postgresql-${PG_MAJOR} \
        postgresql-client-${PG_MAJOR}; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*; \
    test ! -d /var/lib/postgresql/${PG_MAJOR}/main

# Bot dependencies straight from the wheelhouse: no compiler, no network,
# no pip cache and no build toolchain left behind in the final image.
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir --no-index /wheels/*.whl \
 && pip check \
 && rm -rf /wheels

# Bot code + entrypoint + healthcheck. The entrypoint owns the process tree: it
# initializes and starts the local postgres server, waits for it to accept
# connections, then runs the bot. Signals sent to the container reach the
# entrypoint, which shuts the database down cleanly before exiting. Both
# processes run as the unprivileged `app` user (uid 10001), matching the helm
# Pod's runAsNonRoot security context.
COPY entrypoint.sh healthcheck.sh /
WORKDIR /app
COPY . .
RUN useradd --create-home --uid 10001 app \
 && mv /app /opt/app \
 && mkdir -p /data /var/log/postgresql /tmp \
 && chown -R app:app /data /var/log/postgresql \
 && chmod 755 /entrypoint.sh /healthcheck.sh \
 && rm -rf /opt/app/helm /opt/app/.git \
 && chown -R app:app /opt/app
WORKDIR /opt/app
USER app
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "main.py"]
