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