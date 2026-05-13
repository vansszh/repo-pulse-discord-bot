"""Tests for :mod:`repopulse.server`.

We use FastAPI's ``TestClient`` (starlette's, under the hood) to exercise the
HMAC-verified webhook path without starting the bot.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from repopulse.config import Settings
from repopulse.database import Database
from repopulse.dispatcher import EventDispatcher
from repopulse.security import compute_signature
from repopulse.server import create_app


class _StubBot:
    """Minimal stand-in for a discord.Client — the dispatcher never reaches Discord."""

    def get_channel(self, _channel_id: int) -> None:  # pragma: no cover - not hit in unit tests
        return None

    async def fetch_channel(self, _channel_id: int) -> None:  # pragma: no cover
        return None


@pytest.fixture
async def app_client(tmp_path: Path):
    settings = Settings(
        discord_bot_token="test-token",
        github_webhook_secret="test-secret",
        database_path=tmp_path / "t.db",
    )
    db = Database(settings.database_path)
    await db.connect()
    dispatcher = EventDispatcher(bot=_StubBot(), db=db)  # type: ignore[arg-type]
    app = create_app(settings=settings, dispatcher=dispatcher)
    client = TestClient(app)
    try:
        yield client, settings, db
    finally:
        await db.close()


async def test_health_endpoint(app_client) -> None:
    client, _, _ = app_client
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_webhook_rejects_missing_signature(app_client) -> None:
    client, _, _ = app_client
    resp = client.post(
        "/github/webhook",
        json={"zen": "hi"},
        headers={"X-GitHub-Event": "ping"},
    )
    assert resp.status_code == 401


async def test_webhook_rejects_bad_signature(app_client) -> None:
    client, _, _ = app_client
    resp = client.post(
        "/github/webhook",
        json={"zen": "hi"},
        headers={
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": "sha256=deadbeef",
        },
    )
    assert resp.status_code == 401


async def test_webhook_accepts_ping_with_valid_signature(app_client) -> None:
    client, settings, _ = app_client
    payload: dict[str, Any] = {"zen": "hi", "repository": {"full_name": "o/n"}}
    raw = json.dumps(payload).encode()
    sig = compute_signature(settings.github_webhook_secret, raw)
    resp = client.post(
        "/github/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": sig,
            "X-GitHub-Delivery": "abc",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "delivered_to": 0}


async def test_webhook_rejects_missing_event_header(app_client) -> None:
    client, settings, _ = app_client
    raw = b"{}"
    sig = compute_signature(settings.github_webhook_secret, raw)
    resp = client.post(
        "/github/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
        },
    )
    assert resp.status_code == 400


async def test_webhook_rejects_malformed_json(app_client) -> None:
    client, settings, _ = app_client
    raw = b"not-json"
    sig = compute_signature(settings.github_webhook_secret, raw)
    resp = client.post(
        "/github/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": sig,
        },
    )
    assert resp.status_code == 400
