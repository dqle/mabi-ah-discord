"""
Data access layer for the auction house watchlist, backed by a local
PostgreSQL instance.

Every piece of state the bot needs lives in one row per watched item in the
`ah_items` table: the watchlist entry (name / id / price) plus the polling
bookkeeping used to decide what counts as a "new" listing (`last_match`,
`total_result`, `last_alert_price`, `alerted_listings`).

`POSTGRES_CONNECTION_STRING` comes from the environment. The bot ships with a
PostgreSQL server in the same image/container, so the default just works:

    postgresql://mabi_ah@127.0.0.1:5432/mabi_ah

A brand new (empty) database is a valid starting point: the table is created on
first connection (see SCHEMA below), nothing is bootstrapped by hand.

One connection is shared by the whole bot (the alert loop and the slash-command
callbacks all run on the same event loop thread). It is autocommit: every
statement is its own transaction, which is all this app ever needs.
"""

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

import settings

TABLE_NAME = "ah_items"

# Columns shown to users (`/ah_list`, edit/delete lookups) vs. columns the alert
# loop needs.
WATCHLIST_COLUMNS = "id, name, price, last_alert_price"
POLLING_COLUMNS   = "id, name, price, last_match, total_result, last_alert_price, alerted_listings"

# Applied on every connect(), so an empty database is a valid starting point and
# an old volume is upgraded in place. `IF NOT EXISTS` keeps it idempotent.
SCHEMA = """
CREATE TABLE IF NOT EXISTS ah_items (
    id               BIGINT PRIMARY KEY,
    name             TEXT   NOT NULL,
    price            BIGINT NOT NULL,
    last_match       BIGINT NOT NULL,
    total_result     INTEGER NOT NULL DEFAULT 0,
    last_alert_price BIGINT,                 -- cheapest price alerted so far (NULL = never alerted)
    alerted_listings JSONB  NOT NULL DEFAULT '[]'::jsonb
);
"""

connection = None

#-----------------------------------------
# Function: connect()
# Description:
#   Return the shared connection, opening it (and applying SCHEMA) on first
#   use. `reopen=True` closes the current connection first, which is how the
#   alert loop recovers from a server restart.
#-----------------------------------------

def connect(reopen = False):
    global connection

    if connection is not None:
        if not reopen:
            return connection
        close()

    connection = psycopg.connect(
        settings.POSTGRES_CONNECTION_STRING,
        row_factory     = dict_row,          # rows become plain dicts
        connect_timeout = settings.POSTGRES_CONNECT_TIMEOUT_S,
        application_name= "mabi-ah-discord",
    )
    connection.autocommit = True

    # Idempotent: creates the table on a fresh database, no-ops afterwards.
    connection.execute(SCHEMA)

    return connection

def close():
    global connection
    if connection is not None:
        try:
            connection.close()
        except Exception:
            pass    # a dead server is not a shutdown problem
    connection = None

#-----------------------------------------
# Function: get_watchlist() / get_watched_items()
# Description:
#   get_watchlist()     -> user facing columns only (no polling bookkeeping)
#   get_watched_items() -> every column, used by the alert loop
#   Prices come back as ints, alerted_listings as a list of listing ids.
#-----------------------------------------

def get_watchlist():
    return connect().execute(f"SELECT {WATCHLIST_COLUMNS} FROM ah_items ORDER BY name, id").fetchall()

def get_watched_items():
    return connect().execute(f"SELECT {POLLING_COLUMNS} FROM ah_items ORDER BY name, id").fetchall()

#-----------------------------------------
# Function: insert_item()
# Description:
#   Add an item to the watchlist. Re-adding an existing item id is a reset,
#   not a duplicate: the row is reused and the alert history is cleared so the
#   new watch price starts from a clean slate.
#-----------------------------------------

def insert_item(item_id, name, price, last_match, total_result):
    connect().execute(
        """
        INSERT INTO ah_items (id, name, price, last_match, total_result, last_alert_price, alerted_listings)
        VALUES (%s, %s, %s, %s, %s, NULL, '[]'::jsonb)
        ON CONFLICT (id) DO UPDATE SET
            name             = EXCLUDED.name,
            price            = EXCLUDED.price,
            last_match       = EXCLUDED.last_match,
            total_result     = EXCLUDED.total_result,
            last_alert_price = NULL,
            alerted_listings = '[]'::jsonb
        """,
        (int(item_id), str(name), int(price), int(last_match), int(total_result)),
    )

#-----------------------------------------
# Function: update_item()
# Description:
#   Edit the watch price (and/or name) of a watchlist entry. Changing the
#   price resets the alert history, exactly like re-adding the item: the new
#   price has to earn its own alerts.
#-----------------------------------------

def update_item(item_id, new_name, new_price):
    return connect().execute(
        """
        UPDATE ah_items
           SET name             = %s,
               price            = %s,
               last_alert_price = NULL,
               alerted_listings = '[]'::jsonb
         WHERE id = %s
        """,
        (str(new_name), int(new_price), int(item_id)),
    ).rowcount

def update_last_match(item_id, last_match, total_result,
                      last_alert_price = None, alerted_listings = None):
    """
    Persist the polling state for one item.
    The alert bookkeeping is only written when the caller supplies it, so a
    failed MabiBase call cannot wipe the alerted history.
    """
    sets   = ["last_match = %s", "total_result = %s"]
    values = [int(last_match), int(total_result)]

    if last_alert_price is not None:
        sets.append("last_alert_price = %s")
        values.append(int(last_alert_price))
    if alerted_listings is not None:
        sets.append("alerted_listings = %s")
        values.append(Jsonb(sorted(str(listing_id) for listing_id in alerted_listings)))

    values.append(int(item_id))
    connect().execute(f"UPDATE ah_items SET {', '.join(sets)} WHERE id = %s", values)

def delete_item(item_id):
    return connect().execute("DELETE FROM ah_items WHERE id = %s", (int(item_id),)).rowcount

def find_item_by_id(item_id):
    return connect().execute(
        f"SELECT {WATCHLIST_COLUMNS} FROM ah_items WHERE id = %s", (int(item_id),)
    ).fetchone()
