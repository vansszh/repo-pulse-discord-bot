from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from .. import __version__


class MetaCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Check that RepoPulse is alive.")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency_ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            f"🏓 Pong! Gateway latency: **{latency_ms} ms**", ephemeral=True
        )

    @app_commands.command(
        name="help-repopulse",
        description="Show a quick guide to RepoPulse's commands.",
    )
    async def help_repopulse(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="RepoPulse — help",
            description=(
                "Posts real-time GitHub activity from your repositories into Discord "
                "channels, with clean embeds and per-event routing."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Server management",
            value=(
                "`/link-repo repo:owner/name [channel:#…]` — link a GitHub repo.\n"
                "`/unlink-repo repo:owner/name` — stop posting for a repo.\n"
                "`/list-repos` — list linked repos.\n"
                "`/set-channel repo:owner/name event:<type> channel:#…` — route a category.\n"
                "`/review-reminder mode:<enable|disable>` — toggle stale PR reminders."
            ),
            inline=False,
        )
        embed.add_field(
            name="General",
            value="`/ping` — check I'm alive.\n`/help-repopulse` — this message.",
            inline=False,
        )
        embed.add_field(
            name="Event categories",
            value="`issues`, `pulls`, `reviews`, `pushes`, `releases`, `ci`",
            inline=False,
        )
        embed.add_field(
            name="Setup",
            value=(
                "Point a GitHub webhook at `/github/webhook` on the bot's host, "
                "using the shared secret configured via `GITHUB_WEBHOOK_SECRET`."
            ),
            inline=False,
        )
        embed.set_footer(text=f"RepoPulse v{__version__}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MetaCog(bot))
