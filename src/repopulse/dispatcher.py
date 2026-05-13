"""Routes GitHub webhook events to embeds + Discord channels.

The webhook server extracts the raw payload and the ``X-GitHub-Event`` header;
the dispatcher:

1. Builds an embed via :mod:`repopulse.embeds`, or ignores the event.
2. Looks up all guilds that linked this repository.
3. For each guild, resolves the best channel (per-event route → per-repo
   default → per-guild default).
4. Sends the embed.

The dispatcher also opportunistically records PR state into ``known_prs`` so
the stale-PR background task has something to work with.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import discord

from . import embeds
from .database import Database, LinkedRepo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event → (category, builder) mapping
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EventHandler:
    category: str  # one of database.EVENT_CATEGORIES
    builder: Callable[[dict[str, Any]], discord.Embed | None]


_HANDLERS: dict[str, EventHandler] = {
    "issues": EventHandler("issues", embeds.build_issue_embed),
    "pull_request": EventHandler("pulls", embeds.build_pull_request_embed),
    "pull_request_review": EventHandler("reviews", embeds.build_review_embed),
    "push": EventHandler("pushes", embeds.build_push_embed),
    "release": EventHandler("releases", embeds.build_release_embed),
    "workflow_run": EventHandler("ci", embeds.build_workflow_run_embed),
}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class EventDispatcher:
    """Fan-out a GitHub webhook delivery to every Discord channel that wants it."""

    def __init__(self, bot: discord.Client, db: Database) -> None:
        self.bot = bot
        self.db = db

    # ---- public entry point ------------------------------------------------

    async def handle(self, event: str, payload: dict[str, Any]) -> int:
        """Process an event; return the number of channels we posted to."""
        # Ping events are a GitHub connectivity check. Answer with a log and 0.
        if event == "ping":
            logger.info(
                "Received GitHub ping for %s",
                (payload.get("repository") or {}).get("full_name", "?"),
            )
            return 0

        handler = _HANDLERS.get(event)
        if handler is None:
            logger.debug("Ignoring unsupported event type: %s", event)
            return 0

        repo = payload.get("repository") or {}
        owner = (repo.get("owner") or {}).get("login")
        name = repo.get("name")
        if not owner or not name:
            logger.warning("Event %s has no repository info; skipping.", event)
            return 0

        # Update PR state for the reminder task before fanning out.
        await self._track_pr_state(event, payload, owner, name)

        embed = handler.builder(payload)
        if embed is None:
            logger.debug("Handler for %s/%s returned no embed (filtered).", event, payload.get("action"))
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
                logger.exception(
                    "Failed delivering %s to guild %d for %s/%s",
                    event, link.guild_id, owner, name,
                )
        return sent

    # ---- helpers -----------------------------------------------------------

    async def _send_to_link(
        self, link: LinkedRepo, category: str, embed: discord.Embed
    ) -> bool:
        channel_id = await self.db.resolve_target_channel(link, category)
        if channel_id is None:
            logger.info(
                "No channel configured for %s/%s (%s) in guild %d.",
                link.owner, link.name, category, link.guild_id,
            )
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
            logger.warning("Channel %d is not messageable.", channel_id)
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
        """Update ``known_prs`` so the reminder task has fresh data.

        We do this on every PR-related event so the table stays consistent
        without us needing to poll GitHub.
        """
        try:
            if event == "pull_request":
                pr = payload.get("pull_request") or {}
                number = pr.get("number")
                if number is None:
                    return
                action = payload.get("action")
                opened_at = _parse_ts(pr.get("created_at"))
                closed = action == "closed" or pr.get("state") == "closed"
                await self.db.upsert_pr(
                    owner=owner,
                    name=name,
                    number=number,
                    title=pr.get("title", ""),
                    url=pr.get("html_url", ""),
                    author=(pr.get("user") or {}).get("login", "unknown"),
                    opened_at=opened_at,
                    closed=closed,
                )
            elif event == "pull_request_review":
                pr = payload.get("pull_request") or {}
                number = pr.get("number")
                if number is None:
                    return
                # Any submitted review counts as "reviewed enough" to silence
                # the stale reminder.
                if payload.get("action") == "submitted":
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


# Re-exported for convenience in tests.
__all__ = ["_HANDLERS", "EventDispatcher", "EventHandler"]

# Ensure asyncio is actually in use (avoids unused-import lint when the file
# is read standalone).
_ = asyncio
