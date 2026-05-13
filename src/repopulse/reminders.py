from __future__ import annotations

import asyncio
import contextlib
import logging

import discord

from .config import Settings
from .database import Database, LinkedRepo, StalePR
from .embeds import build_review_reminder_embed

logger = logging.getLogger(__name__)


class ReviewReminderTask:
    """Periodically nudges stale, unreviewed PRs."""

    def __init__(self, bot: discord.Client, db: Database, settings: Settings) -> None:
        self.bot = bot
        self.db = db
        self.settings = settings
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="repopulse-review-reminders")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task

    async def _run(self) -> None:
        interval = max(60, self.settings.review_reminder_interval_minutes * 60)
        logger.info(
            "Review reminder task started — interval=%ds threshold=%dh",
            interval, self.settings.review_reminder_hours,
        )

        # Non-bot clients (tests) won't have wait_until_ready.
        with contextlib.suppress(AttributeError):
            await self.bot.wait_until_ready()

        while not self._stop_event.is_set():
            try:
                await self._sweep_once()
            except Exception:
                logger.exception("Review reminder sweep failed.")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except TimeoutError:
                continue

    async def _sweep_once(self) -> None:
        stale = await self.db.find_stale_prs(self.settings.review_reminder_hours)
        if not stale:
            return
        logger.info("Found %d stale PR(s) to remind.", len(stale))
        for pr in stale:
            await self._remind_for_pr(pr)

    async def _remind_for_pr(self, pr: StalePR) -> None:
        links = await self.db.find_repo_links(pr.owner, pr.name)
        any_delivered = False
        for link in links:
            guild_cfg = await self.db.get_guild(link.guild_id)
            if guild_cfg is None or not guild_cfg.review_reminders:
                continue
            if await self._post_reminder(link, pr):
                any_delivered = True

        # Mark reminded regardless of delivery so we don't hammer this PR every tick.
        await self.db.mark_pr_reminded(pr.owner, pr.name, pr.number)
        if any_delivered:
            logger.info("Reminded for %s/%s#%d", pr.owner, pr.name, pr.number)

    async def _post_reminder(self, link: LinkedRepo, pr: StalePR) -> bool:
        channel_id = await self.db.resolve_target_channel(link, "reviews")
        if channel_id is None:
            return False

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden):
                return False

        if not isinstance(channel, discord.abc.Messageable):
            return False

        embed = build_review_reminder_embed(
            owner=pr.owner,
            name=pr.name,
            number=pr.number,
            title=pr.title,
            url=pr.url,
            author=pr.author,
            hours=self.settings.review_reminder_hours,
        )
        try:
            await channel.send(embed=embed)
            return True
        except (discord.Forbidden, discord.HTTPException):
            logger.exception("Failed to send reminder to channel %d.", channel_id)
            return False
