"""Process-level orchestration.

Starts the Discord bot, the FastAPI webhook server (uvicorn), and the
stale-PR reminder task in a single asyncio event loop. Graceful shutdown
flows through ``try / finally`` blocks so the SQLite connection is always
closed cleanly.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from typing import Any

import uvicorn

from .bot import RepoPulseBot
from .config import Settings, get_settings
from .database import Database
from .dispatcher import EventDispatcher
from .logging_setup import setup_logging
from .reminders import ReviewReminderTask
from .server import create_app

logger = logging.getLogger(__name__)


async def _run_uvicorn(app: Any, host: str, port: int) -> None:
    """Run uvicorn inside the running asyncio loop."""
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_config=None,     # inherit our logging setup
        access_log=False,    # keep logs quiet; FastAPI handler already logs deliveries
        lifespan="on",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run(settings: Settings | None = None) -> None:
    """Async entrypoint. Start the bot + server + reminder task."""
    settings = settings or get_settings()
    setup_logging(settings.log_level)
    logger.info("Starting RepoPulse…")

    db = Database(settings.database_path)
    await db.connect()

    bot = RepoPulseBot(settings=settings, db=db)
    dispatcher = EventDispatcher(bot=bot, db=db)
    reminders = ReviewReminderTask(bot=bot, db=db, settings=settings)
    app = create_app(settings=settings, dispatcher=dispatcher)

    bot_task = asyncio.create_task(
        bot.start(settings.discord_bot_token), name="repopulse-bot"
    )
    server_task = asyncio.create_task(
        _run_uvicorn(app, settings.webhook_host, settings.webhook_port),
        name="repopulse-webhook",
    )
    reminders.start()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _request_stop(*_: Any) -> None:
        logger.info("Shutdown signal received.")
        stop.set()

    # SIGINT always works; SIGTERM only on POSIX. Best-effort on Windows.
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, _request_stop)
        except (NotImplementedError, RuntimeError):
            # Windows doesn't support add_signal_handler — KeyboardInterrupt still works.
            pass

    try:
        done, _ = await asyncio.wait(
            {bot_task, server_task, asyncio.create_task(stop.wait())},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            exc = task.exception() if not task.cancelled() else None
            if exc:
                logger.error("Task %s raised: %r", task.get_name(), exc)
    finally:
        logger.info("Shutting down…")
        await reminders.stop()
        if not bot_task.done():
            await bot.close()
        if not server_task.done():
            server_task.cancel()
        for task in (bot_task, server_task):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        await db.close()
        logger.info("Bye.")


def main() -> None:
    """Sync entrypoint for ``python -m repopulse`` and the ``repopulse`` script."""
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        # asyncio.run already handled cleanup via the finally in run().
        pass


if __name__ == "__main__":
    main()
