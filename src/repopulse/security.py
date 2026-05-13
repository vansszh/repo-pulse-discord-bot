"""GitHub webhook signature verification.

GitHub signs every webhook delivery with HMAC-SHA256 in the
``X-Hub-Signature-256`` header (format: ``sha256=<hex>``). We recompute the
signature using the shared secret and compare it in constant time to reject
spoofed / replayed requests.

Docs: https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
"""

from __future__ import annotations

import hashlib
import hmac

_PREFIX = "sha256="


def verify_signature(secret: str, payload: bytes, signature_header: str | None) -> bool:
    """Return ``True`` iff the HMAC-SHA256 of ``payload`` matches ``signature_header``.

    Parameters
    ----------
    secret:
        The shared webhook secret configured both on GitHub and in the bot.
    payload:
        The raw request body bytes (must be the exact bytes GitHub sent, not a
        re-serialized dict).
    signature_header:
        Value of the ``X-Hub-Signature-256`` header, e.g. ``"sha256=abc123..."``.
        ``None`` or malformed values always return ``False``.
    """

    if not secret:
        # Refusing to accept any webhook when no secret is configured is safer
        # than silently allowing unauthenticated traffic.
        return False
    if not signature_header or not signature_header.startswith(_PREFIX):
        return False

    sent_digest = signature_header[len(_PREFIX):]
    expected_digest = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(sent_digest, expected_digest)


def compute_signature(secret: str, payload: bytes) -> str:
    """Return the ``sha256=<hex>`` signature for ``payload``. Mostly used in tests."""

    digest = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"{_PREFIX}{digest}"
