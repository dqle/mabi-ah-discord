# mabi-ah-discord
Mabinogi Auction House Watcher using a Discord Bot + a local PostgreSQL database

This Discord Bot queries items from [MabiBase](https://na.mabibase.com/) and alerts a Discord channel when a new item is listed that matches the alert criteria. It has the same function as the MabiBase built-in alert bot, with two differences:

* MabiBase alerts on a 5 minute interval, this bot polls every `AH_ALERT_INTERVAL` seconds (default 5).
* MabiBase alerts **everyone** subscribed to the item, so popular items are hotly contested. This bot alerts only you, which gives you an edge when buying items at a good price.

https://github.com/user-attachments/assets/358889d6-3a1b-47ae-baa8-946c385c0714

When an item is posted on the Auction House and matches the criteria:

<img src="./repo_media/alert-match.png" width=70% height=70% />

## Local database

The watchlist and all alert bookkeeping live in PostgreSQL, in one row per watched item (`ah_items`):

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | `BIGINT` (primary key) | MabiBase item id, the natural key |
| `name` | `TEXT` | name shown in the alert |
| `price` | `BIGINT` | watch price; listings at or above it are not alerted |
| `last_match` | `BIGINT` | end of the last query window, in epoch seconds |
| `total_result` | `INTEGER` | listing count seen in the last query window |
| `last_alert_price` | `BIGINT` | cheapest price alerted so far (`NULL` = never alerted) |
| `alerted_listings` | `JSONB` | `listingId`s already alerted for this item |

The database runs **inside the same image** as the bot (PostgreSQL 15 on `127.0.0.1:5432`), initialized and started by the container entrypoint before the bot. No cloud Postgres, no RDS, no separate database container: `docker run` / `docker compose up` gives the bot a local database, and `POSTGRES_CONNECTION_STRING` only needs a value when you want to point the bot at some other PostgreSQL.

The table is created on first connection (`CREATE TABLE IF NOT EXISTS`, see `database.SCHEMA`), so an empty database is a valid starting point.

By default the server listens on the loopback interface only, is never published, and trusts local connections - the bot is its only client. See [Securing the local database](#securing-the-local-database) for locking that down.

### Migrating from MongoDB

v1.1.0 replaced MongoDB with PostgreSQL. Nothing to migrate by hand, and no upgrade path from a MongoDB volume: start the new version with an empty volume and re-add your watchlist (`/ah_add_item`), which takes a minute. `docker compose down -v` clears the old one, and in helm the mount point moved from `/data/db` to `/data`, so install the new release with `persistence.enabled: false` (or a fresh release name) the first time.

## Alert rules

Each Auction House **listing** is alerted at most once, and all listings found in one polling cycle are collapsed into a **single embed** (max 1 message per watched item per cycle). Alerting is driven by `listingId` (tracked in the `alerted_listings` column) and `last_alert_price` records the cheapest price alerted so far:

| Situation | Result |
| --- | --- |
| Cheap listing stays visible across many polling cycles | Alert once |
| A new listing appears at the same low price | Alerts again (it is a separate `listingId`) |
| New listing priced at or above the watch price | No alert |
| 7 new listings appear at once | One embed, not 7 messages |

The embed shows the headline cheapest price plus a collapsed price summary (`1 x3, 5, 95, 5,000 x2`) of the new listings **and** of every other listing still in the query window. The number of price levels shown is set by `AH_ALERT_SUMMARY_SIZE` (default 5).

# How to use

## Creating and Inviting a Private Discord Bot

1. Navigate to https://discord.com/developers/applications to create a new bot
2. Click on `New Application` on top right
3. Enter name for your Discord bot, accept ToS and click `Create`
4. Go to `OAuth2` tab on the left and perform the following:
  - Under `Client Information`:
    - Click on `Reset Secret`
  - Under `OAuth2 URL Generator`:
    - Check `Bot`
  - Under `Bot Permissions`:
    - Check `Administrator` 
  - Under `Integration Type`:
    - Select `Guild Install`
5. This will generate an invite link. Copy this and paste to your browser. Select the server you want to add this bot to and click `Continue` and then `Authorize`
6. Go back to the Developer Portal. Go to `Installation` on the left and select `None` in the dropdown under `Install Link`
7. Go to `Bot` tab on the left and perform the following:
  - Under `Authorization Flow`:
    - Disable `Public Bot`
    - Enable `Requires OAUTH2 Code Grant`
  - Under `Priviledged Gateway Intents`:
    - Enable `Presence Intent`
    - Enable `Server Members Intent`
    - Enable `Message Content Intent`
  - Under `Bot Permissions`:
    - Check `Administrator` 
8. Generate a `Token` by going to `Bot` tab and click on `Reset Token` under `Token`. Save this token to use for the app.

## Usage - Docker (recommended, no database to install)

1. Create a `.env` file in the repo root:
```
DISCORD_API_TOKEN = ""
DISCORD_SERVER_ID = ""
DISCORD_CHANNEL_ID = ""
```
 - `DISCORD_API_TOKEN` is generated from step 8 of [Creating and Inviting a Private Discord Bot](#creating-and-inviting-a-private-discord-bot) Section
 - `DISCORD_SERVER_ID` can be found by right click your server where you add the bot and click `Copy Server ID`
 - `DISCORD_CHANNEL_ID` is the channel where you want the alert to go to. This can be found by right click your channel and click `Copy Channel ID`

2. Build and run:

```
docker compose up -d --build
```

That is the whole setup: the container runs `initdb` on an empty volume, starts its own PostgreSQL on `127.0.0.1:5432` and then the bot. The compose file mounts a named volume at `/data` so the watchlist survives restarts; `docker compose down` keeps it, `docker compose down -v` deletes it (and the next start is a fresh, empty database).

Check it is healthy:

```
docker compose ps
docker compose logs -f
docker exec $(docker compose ps -q) /healthcheck.sh
```

## Usage - Local

1. Clone this repo

```
git clone https://github.com/dqle/mabi-ah-discord.git
```

2. Install PostgreSQL locally. The bot needs a PostgreSQL server it can reach on `localhost:5432` with a database it may write to (any recent version works; the container image ships 15).
    - **Docker, one-off container**: `docker run -d --name postgres -e POSTGRES_USER=mabi_ah -e POSTGRES_DB=mabi_ah -e POSTGRES_HOST_AUTH_METHOD=trust -p 127.0.0.1:5432:5432 -v mabi-ah-db:/var/lib/postgresql/postgresql/data postgres:15`
    - **Windows**: install PostgreSQL from https://www.postgresql.org/download/windows/ (the installer registers `postgresql-x64-15` as a service and defaults to `localhost:5432`), then create the role and database once: `psql -U postgres -c "CREATE ROLE mabi_ah LOGIN" -c "CREATE DATABASE mabi_ah OWNER mabi_ah"`
    - **macOS**: `brew install postgresql@15 && brew services start postgresql@15 && createdb mabi_ah`
    - **Debian/Ubuntu**: `apt-get install -y postgresql && sudo -u postgres createuser mabi_ah && sudo -u postgres createdb mabi_ah`

3. Create a `.env` file containing the following:
```
DISCORD_API_TOKEN            = ""
DISCORD_SERVER_ID            = ""
DISCORD_CHANNEL_ID           = ""
POSTGRES_CONNECTION_STRING   = "postgresql://mabi_ah@127.0.0.1:5432/mabi_ah"
AH_ALERT_INTERVAL            = "5"   # optional: polling interval in seconds (default 5)
AH_ALERT_SUMMARY_SIZE        = "5"   # optional: price levels shown in the alert summary (default 5)
```
 - `POSTGRES_CONNECTION_STRING` is the connection string of your local PostgreSQL. The value above is the default baked into `settings.py`, so the line can be omitted for a server on `127.0.0.1:5432` with a `mabi_ah` role and database
 - Point it anywhere else to use a different server, e.g. `postgresql://db-host:5432/mabi_ah` or a managed provider's URI. Add credentials as `postgresql://user:password@host:5432/mabi_ah`. Any libpq parameter works in the URI's query string too, e.g. `?sslmode=require&connect_timeout=10`
 - The bot only needs `SELECT/INSERT/UPDATE/DELETE` on one table; it creates that table itself, so the role needs `CREATE` on the schema of its database (the `public` schema by default)

 4. Install requirements and run the program:
 ```
  pip install -r .\requirements.txt
  python.exe .\main.py #Windows
 ```

## Usage - Helm Chart

The chart runs the bot as a single `Recreate` Pod (never more than one replica: two bots double the alerts, and two Pods cannot share the database volume). The PostgreSQL server is the one inside the container, and its data directory is backed by a PersistentVolumeClaim so the watchlist survives pod restarts.

1. Create a `values.yaml` file containing the following:

```
env:
  DISCORD_API_TOKEN: ""
  DISCORD_SERVER_ID: ""
  DISCORD_CHANNEL_ID: ""
  POSTGRES_CONNECTION_STRING: "postgresql://mabi_ah@127.0.0.1:5432/mabi_ah"
  AH_ALERT_INTERVAL: "5"       # optional: polling interval in seconds (default 5)
  AH_ALERT_SUMMARY_SIZE: "5"   # optional: price levels shown in the alert summary (default 5)
persistence:
  enabled: true
  size: 1Gi
  # storageClassName: standard
resources:
  limits:
    cpu: 1000m
    memory: 512Mi
  requests:
    cpu: 100m
    memory: 256Mi
```

2. Add helm chart:

```
helm repo add dqle https://dqle.github.io/helm-charts/
helm repo update
```

3. Install helm chart:
```
helm install mabi-ah-discord dqle/mabi-ah-discord -f values.yaml -n mabi-ah-discord --create-namespace
```

`persistence.enabled: false` gives an ephemeral database: `initdb` runs again on every pod start and the watchlist is rebuilt from empty, which is fine for a throwaway install. `helm test <release>` checks MabiBase reachability and the database connection.

## Configuration reference

| Variable | Default | Meaning |
| --- | --- | --- |
| `DISCORD_API_TOKEN` | - | Discord bot token (required) |
| `DISCORD_SERVER_ID` | - | guild id the slash commands are registered in (required) |
| `DISCORD_CHANNEL_ID` | - | channel alerts are sent to (required) |
| `POSTGRES_CONNECTION_STRING` | `postgresql://mabi_ah@127.0.0.1:5432/mabi_ah` | the database to use (any libpq URI, incl. `user:password@`, `sslmode`, ...) |
| `POSTGRES_CONNECT_TIMEOUT_S` | `10` | how long libpq waits for a new connection |
| `AH_ALERT_INTERVAL` | `5` | polling interval in seconds |
| `AH_ALERT_SUMMARY_SIZE` | `5` | price levels in the alert summary |
| `PGDATA` | `/data/pgdata` | (container) cluster data directory, on the `/data` volume |
| `PG_PORT` | `5432` | (container) server port, loopback only |
| `PG_USER` / `PG_DATABASE` | `mabi_ah` | (container) initdb role and database |
| `PG_SHARED_BUFFERS` | `64MB` | (container) shared_buffers, keep it well under the memory limit |
| `PG_WORK_MEM` | `4MB` | (container) work_mem per query |
| `PG_LOG_DIR` | `/var/log/postgresql` | (container) server log directory |

## Securing the local database

The in-container server binds to `127.0.0.1` only, its port is never published, and it uses `trust` authentication: fine for a single-user bot on your own machine, and the entrypoint is what creates and starts it. If you want passwords and TLS on the local cluster, set `POSTGRES_CONNECTION_STRING` to a `user:password@host` URI and change the `--auth-local`/`--auth-host` flags in `entrypoint.sh` (`scram-sha-256`), then let `initdb` and `psql` set the role password. Point the connection string at an external/managed PostgreSQL instead if you want a server someone else operates - nothing else in the bot changes.

## Commands

| Command | Effect |
| --- | --- |
| `/ah_list` | every watched item, its target price and last alert price |
| `/ah_add_item` | Add Item modal: name, item id, price |
| `/ah_edit_item <item_id>` | Edit modal for one item |
| `/ah_delete_item <item_id>` | remove an item from the watchlist |
| `!ah_ping` | chat command, answers `pong` |

Adding an item id that is already watched resets it (new watch price, empty alert history) instead of creating a duplicate. Editing the price also resets the alert history, so the new price has to earn its own alerts.
