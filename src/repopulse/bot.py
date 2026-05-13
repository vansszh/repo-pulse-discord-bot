"""Discord bot client for RepoPulse.

Builds a :class:`discord.ext.commands.Bot`, registers cogs, and syncs slash
commands on ``on_ready``. The bot is started from :mod:`repopulse.runner`
alongside the FastAPI webhook server.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .cogs import management, meta
from .config import Settings
from .database import Database

logger = logging.getLogger(__name__)


def _build_intents() -> discord.Intents:
    """Intents tell Discord which events we want to receive.

    RepoPulse is push-driven (it sends, rarely reads), so we request the
    minimal ``default`` set. No privileged intents (members / message content)
    are needed and requesting them would require extra portal approval.
    """
    intents = discord.Intents.default()
    intents.message_content = False
    intents.members = False
    intents.presences = False
    return intents


class RepoPulseBot(commands.Bot):
    """The RepoPulse bot client."""

    def __init__(self, settings: Settings, db: Database) -> None:
        super().__init__(
            command_prefix="!",  # unused — we only expose slash commands
            intents=_build_intents(),
            help_command=None,
        )
        self.settings = settings
        self.db = db

    async def setup_hook(self) -> None:
        """Register cogs and sync application commands.

        ``setup_hook`` runs once before the bot connects to the gateway.
        """
        await management.setup(self, self.db)
        await meta.setup(self)

        dev_guilds = self.settings.dev_guild_id_list
        if dev_guilds:
            # Per-guild sync is instant and ideal during development.
            for gid in dev_guilds:
                guild = discord.Object(id=gid)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logger.info("Synced %d command(s) to dev guild %d", len(synced), gid)
        else:
            # Global sync — can take up to ~1 hour to propagate, but covers all servers.
            synced = await self.tree.sync()
            logger.info("Synced %d global command(s)", len(synced))

    async def on_ready(self) -> None:
        assert self.user is not None
        logger.info(
            "Logged in as %s (id=%s). Connected to %d guild(s).",
            self.user,
            self.user.id,
            len(self.guilds),
        )
        activity = discord.Activity(
            type=discord.ActivityType.watching, name="GitHub activity"
        )
        await self.change_presence(activity=activity, status=discord.Status.online)
