from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .cogs import management, meta
from .config import Settings
from .database import Database

logger = logging.getLogger(__name__)


def _build_intents() -> discord.Intents:
    # This bot is push-only — no privileged intents needed.
    intents = discord.Intents.default()
    intents.message_content = False
    intents.members = False
    intents.presences = False
    return intents


class RepoPulseBot(commands.Bot):
    def __init__(self, settings: Settings, db: Database) -> None:
        super().__init__(
            command_prefix="!",  # unused; we only ship slash commands
            intents=_build_intents(),
            help_command=None,
        )
        self.settings = settings
        self.db = db

    async def setup_hook(self) -> None:
        await management.setup(self, self.db)
        await meta.setup(self)

        dev_guilds = self.settings.dev_guild_id_list
        if dev_guilds:
            # Per-guild sync is instant — handy during development.
            for gid in dev_guilds:
                guild = discord.Object(id=gid)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logger.info("Synced %d command(s) to dev guild %d", len(synced), gid)
        else:
            # Global sync can take up to an hour to propagate.
            synced = await self.tree.sync()
            logger.info("Synced %d global command(s)", len(synced))

    async def on_ready(self) -> None:
        assert self.user is not None
        logger.info(
            "Logged in as %s (id=%s). Connected to %d guild(s).",
            self.user, self.user.id, len(self.guilds),
        )
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="GitHub activity"),
            status=discord.Status.online,
        )
