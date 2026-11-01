import os
import logging
import discord
from dotenv import load_dotenv
from logging.config import dictConfig

load_dotenv()
DISCORD_API_TOKEN         = os.getenv("DISCORD_API_TOKEN")
DISCORD_SERVER_ID         = discord.Object(id=int(os.getenv("DISCORD_SERVER_ID")))
DISCORD_CHANNEL_ID        = int(os.getenv("DISCORD_CHANNEL_ID"))
MONGODB_CONNECTION_STRING = os.getenv("MONGODB_CONNECTION_STRING")

def _env_int(name, default):
    """Read an int env var, tolerating unset/empty values (helm renders empty strings)."""
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default

# How often (in seconds) the alert loop polls MabiBase per watched item
AH_ALERT_INTERVAL = _env_int("AH_ALERT_INTERVAL", 5)

# How many distinct price levels are listed in the alert message price summary
AH_ALERT_SUMMARY_SIZE = _env_int("AH_ALERT_SUMMARY_SIZE", 5)

LOGGING_CONFIG = {
    "version": 1,
    "disabled_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)-10s - %(asctime)s - %(module)-15s : %(message)s"
        },
        "standard": {"format": "%(levelname)-10s - %(name)-15s : %(message)s"},
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        "console2": {
            "level": "WARNING",
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },
    "loggers": {
        "bot": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "discord": {
            "handlers": ["console2"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

dictConfig(LOGGING_CONFIG)