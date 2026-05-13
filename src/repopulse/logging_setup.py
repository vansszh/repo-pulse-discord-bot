from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            "%Y-%m-%d %H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric)

    # Quiet down chatty libs unless we want everything.
    if numeric > logging.DEBUG:
        for name in ("discord", "discord.gateway", "discord.client", "httpx", "httpcore"):
            logging.getLogger(name).setLevel(logging.WARNING)
