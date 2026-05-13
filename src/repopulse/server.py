"""FastAPI webhook server for GitHub deliveries.

Responsibilities:

* Expose ``POST /github/webhook`` for GitHub to deliver events to.
* Verify each delivery's HMAC-SHA256 signature.
* Hand parsed payloads to :class:`repopulse.dispatcher.EventDispatcher`.
* Provide simple ``GET /health`` and ``GET /`` endpoints.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from . import __version__
from .config import Settings
from .dispatcher import EventDispatcher
from .security import verify_signature

logger = logging.getLogger(__name__)


def create_app(settings: Settings, dispatcher: EventDispatcher) -> FastAPI:
    """Build the FastAPI application."""
    app = FastAPI(
        title="RepoPulse Webhook Server",
        version=__version__,
        docs_url=None,       # no public API docs — this endpoint is for GitHub only
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": "repopulse", "version": __version__}

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/github/webhook")
    async def github_webhook(
        request: Request,
        x_github_event: str | None = Header(default=None),
        x_hub_signature_256: str | None = Header(default=None),
        x_github_delivery: str | None = Header(default=None),
    ) -> JSONResponse:
        raw = await request.body()

        if not verify_signature(settings.github_webhook_secret, raw, x_hub_signature_256):
            logger.warning(
                "Rejected webhook delivery %s (event=%s) — bad signature.",
                x_github_delivery, x_github_event,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature.",
            )

        if not x_github_event:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing X-GitHub-Event header.",
            )

        try:
            payload: dict[str, Any] = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning("Malformed webhook payload: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Body is not valid JSON.",
            ) from exc

        logger.info(
            "Webhook accepted: event=%s delivery=%s action=%s repo=%s",
            x_github_event,
            x_github_delivery,
            payload.get("action"),
            (payload.get("repository") or {}).get("full_name"),
        )

        sent = await dispatcher.handle(x_github_event, payload)
        return JSONResponse({"ok": True, "delivered_to": sent})

    return app
