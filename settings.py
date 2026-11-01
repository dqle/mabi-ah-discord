import os
import logging
import discord
from dotenv import load_dotenv
from logging.config import dictConfig

load_dotenv()


def _env_int(name, default):
    """Read an int env var, tolerating unset/empty values (helm renders empty strings)."""
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


DISCORD_API_TOKEN = os.getenv("DISCORD_API_TOKEN")
DISCORD_SERVER_ID = discord.Object(id=int(os.getenv("DISCORD_SERVER_ID")))
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))

# Local PostgreSQL. The server ships in the same image as the bot (see
# Dockerfile), so the default connection string works out of the box:
#   postgresql://mabi_ah@127.0.0.1:5432/mabi_ah
POSTGRES_CONNECTION_STRING = os.getenv(
    "POSTGRES_CONNECTION_STRING",
    "postgresql://mabi_ah@127.0.0.1:5432/mabi_ah",
)

# How long libpq waits for the server to answer a new connection (seconds)
POSTGRES_CONNECT_TIMEOUT_S = _env_int("POSTGRES_CONNECT_TIMEOUT_S", 10)

# How often (in seconds) the alert loop polls MabiBase per watched item
AH_ALERT_INTERVAL = _env_int("AH_ALERT_INTERVAL", 5)

# How many distinct price levels are listed in the alert message price summary
AH_ALERT_SUMMARY_SIZE = _env_int("AH_ALERT_SUMMARY_SIZE", 5)
