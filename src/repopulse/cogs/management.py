"""Server-management slash commands.

All commands here require the Discord **Manage Server** permission.
"""

from __future__ import annotations

import logging
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from ..database import EVENT_CATEGORIES, Database
from ..utils import parse_repo, truncate

logger = logging.getLogger(__name__)

EventType = Literal["issues", "pulls", "reviews", "pushes", "releases", "ci"]
ReminderMode = Literal["enable", "disable"]


class ManagementCog(commands.Cog):
    """Repository linking, channel routing, and reminder toggles."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    # -- /link-repo -----------------------------------------------------------

    @app_commands.command(
        name="link-repo",
        description="Link a GitHub repository to this server so its events post here.",
    )
    @app_commands.describe(
        repo="owner/repository — e.g. octocat/hello-world",
        channel="Default channel for this repo's events (optional, defaults to current channel).",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def link_repo(
        self,
        interaction: discord.Interaction,
        repo: str,
        channel: discord.TextChannel | None = None,
    ) -> None:
        try:
            owner, name = parse_repo(repo)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        assert interaction.guild_id is not None  # enforced by guild_only
        target_channel = channel or (
            interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None
        )
        channel_id = target_channel.id if target_channel else None

        await self.db.upsert_guild(interaction.guild_id, default_channel_id=channel_id)
        await self.db.link_repo(interaction.guild_id, owner, name, channel_id=channel_id)

        msg = f"✅ Linked **{owner}/{name}**"
        if target_channel:
            msg += f" → {target_channel.mention}"
        msg += (
            "\n\nNow add a GitHub webhook pointing at this bot's "
            "`/github/webhook` endpoint (see the README)."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    # -- /unlink-repo ---------------------------------------------------------

    @app_commands.command(
        name="unlink-repo",
        description="Stop posting events for a previously linked repository.",
    )
    @app_commands.describe(repo="owner/repository — e.g. octocat/hello-world")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def unlink_repo(self, interaction: discord.Interaction, repo: str) -> None:
        try:
            owner, name = parse_repo(repo)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        assert interaction.guild_id is not None
        removed = await self.db.unlink_repo(interaction.guild_id, owner, name)
        if removed:
            await interaction.response.send_message(
                f"🗑️ Unlinked **{owner}/{name}**.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"ℹ️ **{owner}/{name}** was not linked here.", ephemeral=True
            )

    # -- /list-repos ----------------------------------------------------------

    @app_commands.command(
        name="list-repos",
        description="Show the GitHub repositories linked to this server.",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def list_repos(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        repos = await self.db.list_repos(interaction.guild_id)
        if not repos:
            await interaction.response.send_message(
                "No repositories are linked yet. Use `/link-repo` to add one.",
                ephemeral=True,
            )
            return

        lines: list[str] = []
        for r in repos:
            channel_ref = f"<#{r.channel_id}>" if r.channel_id else "_(no default channel)_"
            lines.append(f"• **{r.full_name}** → {channel_ref}")

        embed = discord.Embed(
            title="Linked repositories",
            description=truncate("\n".join(lines), 4000),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"{len(repos)} repo(s) linked")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -- /set-channel ---------------------------------------------------------

    @app_commands.command(
        name="set-channel",
        description="Route a specific event category for a repo to a specific channel.",
    )
    @app_commands.describe(
        repo="owner/repository — e.g. octocat/hello-world",
        event="Which event category to route",
        channel="Where events of that category should be posted",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def set_channel(
        self,
        interaction: discord.Interaction,
        repo: str,
        event: EventType,
        channel: discord.TextChannel,
    ) -> None:
        try:
            owner, name = parse_repo(repo)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return
        if event not in EVENT_CATEGORIES:
            await interaction.response.send_message(
                f"❌ Unknown event `{event}`.", ephemeral=True
            )
            return

        assert interaction.guild_id is not None
        # Auto-link the repo if not already linked, so /set-channel is a
        # single-step workflow.
        await self.db.link_repo(interaction.guild_id, owner, name)
        await self.db.set_channel_route(
            interaction.guild_id, owner, name, event, channel.id
        )
        await interaction.response.send_message(
            f"✅ **{owner}/{name}** → `{event}` events now go to {channel.mention}.",
            ephemeral=True,
        )

    # -- /review-reminder -----------------------------------------------------

    @app_commands.command(
        name="review-reminder",
        description="Enable or disable stale pull request review reminders for this server.",
    )
    @app_commands.describe(mode="enable or disable")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def review_reminder(
        self, interaction: discord.Interaction, mode: ReminderMode
    ) -> None:
        assert interaction.guild_id is not None
        enabled = mode == "enable"
        await self.db.set_review_reminders(interaction.guild_id, enabled)
        status = "enabled ✅" if enabled else "disabled 🛑"
        await interaction.response.send_message(
            f"Review reminders **{status}** for this server.", ephemeral=True
        )


async def setup(bot: commands.Bot, db: Database) -> None:
    await bot.add_cog(ManagementCog(bot, db))
