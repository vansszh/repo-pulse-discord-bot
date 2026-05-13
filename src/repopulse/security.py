from __future__ import annotations

import hashlib
import hmac

_PREFIX = "sha256="


def verify_signature(secret: str, payload: bytes, signature_header: str | None) -> bool:
    """Check a GitHub X-Hub-Signature-256 header against the payload."""
    if not secret:
        # Reject everything if no secret is configured — better than silently allowing.
        return False
    if not signature_header or not signature_header.startswith(_PREFIX):
        return False

    sent = signature_header[len(_PREFIX):]
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sent, expected)


def compute_signature(secret: str, payload: bytes) -> str:
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"{_PREFIX}{digest}"
