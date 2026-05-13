"""Tests for :mod:`repopulse.database`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from repopulse.database import Database, LinkedRepo


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    await database.connect()
    try:
        yield database
    finally:
        await database.close()


async def test_link_and_list_repos(db: Database) -> None:
    await db.link_repo(guild_id=1, owner="octocat", name="hello", channel_id=100)
    await db.link_repo(guild_id=1, owner="octocat", name="world", channel_id=200)
    repos = await db.list_repos(1)
    names = {r.full_name for r in repos}
    assert names == {"octocat/hello", "octocat/world"}


async def test_link_is_case_insensitive(db: Database) -> None:
    await db.link_repo(guild_id=1, owner="OctoCat", name="Hello", channel_id=10)
    links = await db.find_repo_links("octocat", "hello")
    assert len(links) == 1
    assert links[0].owner == "octocat"
    assert links[0].name == "hello"


async def test_unlink_removes_row_and_routes(db: Database) -> None:
    await db.link_repo(guild_id=1, owner="o", name="n", channel_id=10)
    await db.set_channel_route(1, "o", "n", "issues", 500)
    removed = await db.unlink_repo(1, "o", "n")
    assert removed is True
    assert await db.list_repos(1) == []
    assert await db.get_channel_route(1, "o", "n", "issues") is None


async def test_unlink_of_unknown_repo_returns_false(db: Database) -> None:
    removed = await db.unlink_repo(1, "missing", "repo")
    assert removed is False


async def test_resolve_target_channel_prefers_per_event_route(db: Database) -> None:
    await db.upsert_guild(1, default_channel_id=1000)
    await db.link_repo(1, "o", "n", channel_id=2000)
    await db.set_channel_route(1, "o", "n", "issues", 3000)
    link = LinkedRepo(guild_id=1, owner="o", name="n", channel_id=2000)
    assert await db.resolve_target_channel(link, "issues") == 3000


async def test_resolve_target_channel_falls_back_to_repo_default(db: Database) -> None:
    await db.upsert_guild(1, default_channel_id=1000)
    await db.link_repo(1, "o", "n", channel_id=2000)
    link = LinkedRepo(guild_id=1, owner="o", name="n", channel_id=2000)
    assert await db.resolve_target_channel(link, "pulls") == 2000


async def test_resolve_target_channel_falls_back_to_guild_default(db: Database) -> None:
    await db.upsert_guild(1, default_channel_id=1000)
    await db.link_repo(1, "o", "n")  # no per-repo channel
    link = LinkedRepo(guild_id=1, owner="o", name="n", channel_id=None)
    assert await db.resolve_target_channel(link, "pulls") == 1000


async def test_resolve_target_channel_returns_none_when_nothing_configured(db: Database) -> None:
    link = LinkedRepo(guild_id=999, owner="o", name="n", channel_id=None)
    assert await db.resolve_target_channel(link, "pulls") is None


async def test_review_reminders_toggle(db: Database) -> None:
    await db.set_review_reminders(1, True)
    cfg = await db.get_guild(1)
    assert cfg is not None and cfg.review_reminders is True

    await db.set_review_reminders(1, False)
    cfg = await db.get_guild(1)
    assert cfg is not None and cfg.review_reminders is False


async def test_find_stale_prs(db: Database) -> None:
    now = datetime.now(UTC)
    old = now - timedelta(hours=48)
    recent = now - timedelta(hours=1)

    await db.upsert_pr("o", "n", 1, "old", "u", "a", opened_at=old)
    await db.upsert_pr("o", "n", 2, "recent", "u", "a", opened_at=recent)
    # Already reviewed — should be excluded.
    await db.upsert_pr("o", "n", 3, "reviewed", "u", "a", opened_at=old)
    await db.mark_pr_reviewed("o", "n", 3)
    # Already reminded — should be excluded.
    await db.upsert_pr("o", "n", 4, "reminded", "u", "a", opened_at=old)
    await db.mark_pr_reminded("o", "n", 4)

    stale = await db.find_stale_prs(older_than_hours=24)
    numbers = {p.number for p in stale}
    assert numbers == {1}


async def test_set_channel_route_rejects_unknown_event(db: Database) -> None:
    with pytest.raises(ValueError):
        await db.set_channel_route(1, "o", "n", "bogus", 100)
