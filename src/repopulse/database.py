"""Async SQLite storage for RepoPulse.

Tables
------
``guilds``
    One row per Discord server (guild). Stores default channel and whether
    review reminders are enabled.

``linked_repos``
    (guild_id, owner, name) tuples — which GitHub repos are linked to which
    Discord server. Each link can also override the default channel and
    enable/disable review reminders per repo.

``channel_routes``
    (guild_id, owner, name, event_type) → channel_id overrides. Lets servers
    route different event categories (issues, pulls, ci, releases) to
    different channels.

``known_prs``
    Minimal state about open PRs so the review-reminder background task can
    decide whether to nudge reviewers. Updated opportunistically as we
    receive webhook events.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EVENT_CATEGORIES = ("issues", "pulls", "reviews", "pushes", "releases", "ci")
"""Logical channel-routing buckets exposed via ``/set-channel``."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS guilds (
    guild_id            INTEGER PRIMARY KEY,
    default_channel_id  INTEGER,
    review_reminders    INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS linked_repos (
    guild_id    INTEGER NOT NULL,
    owner       TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    channel_id  INTEGER,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (guild_id, owner, name)
);

CREATE INDEX IF NOT EXISTS idx_linked_repos_by_repo
    ON linked_repos (owner, name);

CREATE TABLE IF NOT EXISTS channel_routes (
    guild_id    INTEGER NOT NULL,
    owner       TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    event_type  TEXT    NOT NULL,
    channel_id  INTEGER NOT NULL,
    PRIMARY KEY (guild_id, owner, name, event_type)
);

CREATE TABLE IF NOT EXISTS known_prs (
    owner       TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    number      INTEGER NOT NULL,
    title       TEXT    NOT NULL,
    url         TEXT    NOT NULL,
    author      TEXT    NOT NULL,
    opened_at   TEXT    NOT NULL,
    last_activity_at TEXT NOT NULL,
    reviewed    INTEGER NOT NULL DEFAULT 0,
    reminded_at TEXT,
    closed      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (owner, name, number)
);
"""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LinkedRepo:
    guild_id: int
    owner: str
    name: str
    channel_id: int | None

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass(slots=True)
class GuildConfig:
    guild_id: int
    default_channel_id: int | None
    review_reminders: bool


@dataclass(slots=True)
class StalePR:
    owner: str
    name: str
    number: int
    title: str
    url: str
    author: str
    opened_at: datetime
    last_activity_at: datetime


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


class Database:
    """Thin async wrapper around an ``aiosqlite`` connection.

    Single long-lived connection. SQLite handles our write volume comfortably
    and serializing writes through one connection keeps things simple.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._conn: aiosqlite.Connection | None = None

    # -- lifecycle ------------------------------------------------------------

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        logger.info("Database ready at %s", self.path)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database.connect() must be called before use.")
        return self._conn

    # -- guilds --------------------------------------------------------------

    async def upsert_guild(self, guild_id: int, default_channel_id: int | None = None) -> None:
        await self.conn.execute(
            """
            INSERT INTO guilds (guild_id, default_channel_id)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                default_channel_id = COALESCE(excluded.default_channel_id, guilds.default_channel_id)
            """,
            (guild_id, default_channel_id),
        )
        await self.conn.commit()

    async def set_review_reminders(self, guild_id: int, enabled: bool) -> None:
        await self.upsert_guild(guild_id)
        await self.conn.execute(
            "UPDATE guilds SET review_reminders = ? WHERE guild_id = ?",
            (1 if enabled else 0, guild_id),
        )
        await self.conn.commit()

    async def get_guild(self, guild_id: int) -> GuildConfig | None:
        async with self.conn.execute(
            "SELECT guild_id, default_channel_id, review_reminders FROM guilds WHERE guild_id = ?",
            (guild_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return GuildConfig(
            guild_id=row["guild_id"],
            default_channel_id=row["default_channel_id"],
            review_reminders=bool(row["review_reminders"]),
        )

    # -- linked repos ---------------------------------------------------------

    async def link_repo(
        self,
        guild_id: int,
        owner: str,
        name: str,
        channel_id: int | None = None,
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO linked_repos (guild_id, owner, name, channel_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, owner, name) DO UPDATE SET
                channel_id = COALESCE(excluded.channel_id, linked_repos.channel_id)
            """,
            (guild_id, owner.lower(), name.lower(), channel_id),
        )
        await self.conn.commit()

    async def unlink_repo(self, guild_id: int, owner: str, name: str) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM linked_repos WHERE guild_id = ? AND owner = ? AND name = ?",
            (guild_id, owner.lower(), name.lower()),
        )
        await self.conn.execute(
            "DELETE FROM channel_routes WHERE guild_id = ? AND owner = ? AND name = ?",
            (guild_id, owner.lower(), name.lower()),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def list_repos(self, guild_id: int) -> list[LinkedRepo]:
        async with self.conn.execute(
            "SELECT guild_id, owner, name, channel_id FROM linked_repos WHERE guild_id = ? ORDER BY owner, name",
            (guild_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [
            LinkedRepo(
                guild_id=r["guild_id"],
                owner=r["owner"],
                name=r["name"],
                channel_id=r["channel_id"],
            )
            for r in rows
        ]

    async def find_repo_links(self, owner: str, name: str) -> list[LinkedRepo]:
        """Find all (guild, channel) links for a given GitHub repo.

        Used by the webhook dispatcher to fan out a single GitHub event to
        every Discord server that has linked this repo.
        """
        async with self.conn.execute(
            "SELECT guild_id, owner, name, channel_id FROM linked_repos WHERE owner = ? AND name = ?",
            (owner.lower(), name.lower()),
        ) as cur:
            rows = await cur.fetchall()
        return [
            LinkedRepo(
                guild_id=r["guild_id"],
                owner=r["owner"],
                name=r["name"],
                channel_id=r["channel_id"],
            )
            for r in rows
        ]

    # -- channel routes -------------------------------------------------------

    async def set_channel_route(
        self,
        guild_id: int,
        owner: str,
        name: str,
        event_type: str,
        channel_id: int,
    ) -> None:
        if event_type not in EVENT_CATEGORIES:
            raise ValueError(f"Unknown event_type: {event_type}")
        await self.conn.execute(
            """
            INSERT INTO channel_routes (guild_id, owner, name, event_type, channel_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, owner, name, event_type) DO UPDATE SET
                channel_id = excluded.channel_id
            """,
            (guild_id, owner.lower(), name.lower(), event_type, channel_id),
        )
        await self.conn.commit()

    async def get_channel_route(
        self,
        guild_id: int,
        owner: str,
        name: str,
        event_type: str,
    ) -> int | None:
        async with self.conn.execute(
            """
            SELECT channel_id FROM channel_routes
            WHERE guild_id = ? AND owner = ? AND name = ? AND event_type = ?
            """,
            (guild_id, owner.lower(), name.lower(), event_type),
        ) as cur:
            row = await cur.fetchone()
        return row["channel_id"] if row else None

    async def resolve_target_channel(
        self,
        link: LinkedRepo,
        event_type: str,
    ) -> int | None:
        """Pick the best channel for ``event_type`` on ``link``.

        Resolution order:

        1. Per-repo per-event route (``channel_routes``).
        2. Per-repo default channel (``linked_repos.channel_id``).
        3. Per-guild default channel (``guilds.default_channel_id``).
        4. ``None`` — nothing configured, skip delivery.
        """
        route = await self.get_channel_route(link.guild_id, link.owner, link.name, event_type)
        if route is not None:
            return route
        if link.channel_id is not None:
            return link.channel_id
        guild = await self.get_guild(link.guild_id)
        return guild.default_channel_id if guild else None

    # -- known PRs ------------------------------------------------------------

    async def upsert_pr(
        self,
        owner: str,
        name: str,
        number: int,
        title: str,
        url: str,
        author: str,
        opened_at: datetime,
        reviewed: bool = False,
        closed: bool = False,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        await self.conn.execute(
            """
            INSERT INTO known_prs (
                owner, name, number, title, url, author,
                opened_at, last_activity_at, reviewed, closed
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner, name, number) DO UPDATE SET
                title            = excluded.title,
                url              = excluded.url,
                last_activity_at = excluded.last_activity_at,
                reviewed         = known_prs.reviewed OR excluded.reviewed,
                closed           = excluded.closed
            """,
            (
                owner.lower(),
                name.lower(),
                number,
                title,
                url,
                author,
                opened_at.isoformat(),
                now,
                1 if reviewed else 0,
                1 if closed else 0,
            ),
        )
        await self.conn.commit()

    async def mark_pr_reviewed(self, owner: str, name: str, number: int) -> None:
        now = datetime.now(UTC).isoformat()
        await self.conn.execute(
            """
            UPDATE known_prs
            SET reviewed = 1, last_activity_at = ?
            WHERE owner = ? AND name = ? AND number = ?
            """,
            (now, owner.lower(), name.lower(), number),
        )
        await self.conn.commit()

    async def mark_pr_reminded(self, owner: str, name: str, number: int) -> None:
        now = datetime.now(UTC).isoformat()
        await self.conn.execute(
            "UPDATE known_prs SET reminded_at = ? WHERE owner = ? AND name = ? AND number = ?",
            (now, owner.lower(), name.lower(), number),
        )
        await self.conn.commit()

    async def find_stale_prs(self, older_than_hours: int) -> list[StalePR]:
        """PRs that are open, unreviewed, not reminded yet, and older than the threshold."""
        cutoff = datetime.now(UTC).timestamp() - older_than_hours * 3600
        async with self.conn.execute(
            """
            SELECT owner, name, number, title, url, author, opened_at, last_activity_at
            FROM known_prs
            WHERE closed = 0
              AND reviewed = 0
              AND reminded_at IS NULL
            """
        ) as cur:
            rows = await cur.fetchall()

        stale: list[StalePR] = []
        for r in rows:
            opened_at = datetime.fromisoformat(r["opened_at"])
            if opened_at.timestamp() > cutoff:
                continue
            stale.append(
                StalePR(
                    owner=r["owner"],
                    name=r["name"],
                    number=r["number"],
                    title=r["title"],
                    url=r["url"],
                    author=r["author"],
                    opened_at=opened_at,
                    last_activity_at=datetime.fromisoformat(r["last_activity_at"]),
                )
            )
        return stale
