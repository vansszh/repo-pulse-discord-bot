"""Central logging configuration.

Call :func:`setup_logging` once at process startup. All modules should then
obtain a logger via ``logging.getLogger(__name__)``.
"""

from __future__ import annotations

import logging
import sys

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger with a concise, single-line format."""

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter(fmt=_FORMAT, datefmt=_DATEFMT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric_level)

    # Tone down noisy third-party loggers unless we're explicitly in DEBUG.
    if numeric_level > logging.DEBUG:
        for noisy in ("discord", "discord.gateway", "discord.client", "httpx", "httpcore"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
