from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import discord

from . import embeds
from .database import Database, LinkedRepo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EventHandler:
    category: str
    builder: Callable[[dict[str, Any]], discord.Embed | None]


_HANDLERS: dict[str, EventHandler] = {
    "issues": EventHandler("issues", embeds.build_issue_embed),
    "pull_request": EventHandler("pulls", embeds.build_pull_request_embed),
    "pull_request_review": EventHandler("reviews", embeds.build_review_embed),
    "push": EventHandler("pushes", embeds.build_push_embed),
    "release": EventHandler("releases", embeds.build_release_embed),
    "workflow_run": EventHandler("ci", embeds.build_workflow_run_embed),
}


class EventDispatcher:
    """Turn a GitHub webhook into Discord messages."""

    def __init__(self, bot: discord.Client, db: Database) -> None:
        self.bot = bot
        self.db = db

    async def handle(self, event: str, payload: dict[str, Any]) -> int:
        if event == "ping":
            logger.info(
                "GitHub ping for %s",
                (payload.get("repository") or {}).get("full_name", "?"),
            )
            return 0

        handler = _HANDLERS.get(event)
        if handler is None:
            logger.debug("Ignoring unsupported event: %s", event)
            return 0

        repo = payload.get("repository") or {}
        owner = (repo.get("owner") or {}).get("login")
        name = repo.get("name")
        if not owner or not name:
            logger.warning("Event %s has no repository info; skipping.", event)
            return 0

        await self._track_pr_state(event, payload, owner, name)

        embed = handler.builder(payload)
        if embed is None:
            return 0

        links = await self.db.find_repo_links(owner, name)
        if not links:
            logger.info("No Discord guilds link %s/%s; dropping event.", owner, name)
            return 0

        sent = 0
        for link in links:
            try:
                if await self._send_to_link(link, handler.category, embed):
                    sent += 1
            except Exception:
                # One bad guild must not take down the fan-out for everyone else.
                logger.exception(
                    "Failed delivering %s to guild %d for %s/%s",
                    event, link.guild_id, owner, name,
                )
        return sent

    async def _send_to_link(
        self, link: LinkedRepo, category: str, embed: discord.Embed
    ) -> bool:
        channel_id = await self.db.resolve_target_channel(link, category)
        if channel_id is None:
            return False

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.NotFound:
                logger.warning("Channel %d not found; skipping.", channel_id)
                return False
            except discord.Forbidden:
                logger.warning("No access to channel %d; skipping.", channel_id)
                return False

        if not isinstance(channel, discord.abc.Messageable):
            return False

        try:
            await channel.send(embed=embed)
            return True
        except discord.Forbidden:
            logger.warning("Forbidden when sending to channel %d.", channel_id)
            return False
        except discord.HTTPException:
            logger.exception("Discord HTTP error when sending to channel %d.", channel_id)
            return False

    async def _track_pr_state(
        self, event: str, payload: dict[str, Any], owner: str, name: str
    ) -> None:
        # Keep known_prs in sync so the reminder task has accurate data.
        try:
            if event == "pull_request":
                pr = payload.get("pull_request") or {}
                number = pr.get("number")
                if number is None:
                    return
                action = payload.get("action")
                closed = action == "closed" or pr.get("state") == "closed"
                await self.db.upsert_pr(
                    owner=owner,
                    name=name,
                    number=number,
                    title=pr.get("title", ""),
                    url=pr.get("html_url", ""),
                    author=(pr.get("user") or {}).get("login", "unknown"),
                    opened_at=_parse_ts(pr.get("created_at")),
                    closed=closed,
                )
            elif event == "pull_request_review" and payload.get("action") == "submitted":
                pr = payload.get("pull_request") or {}
                number = pr.get("number")
                if number is not None:
                    await self.db.mark_pr_reviewed(owner, name, number)
        except Exception:
            logger.exception("Failed to track PR state for %s/%s", owner, name)


def _parse_ts(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)


__all__ = ["_HANDLERS", "EventDispatcher", "EventHandler"]
