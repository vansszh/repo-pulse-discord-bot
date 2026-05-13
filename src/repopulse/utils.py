"""Small helpers shared between the bot and the webhook server."""

from __future__ import annotations

import re

# GitHub repo names: alphanumeric, hyphen, underscore, period. Length 1-100.
# Owner names: alphanumeric and single hyphens, 1-39 chars.
_REPO_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")


def parse_repo(value: str) -> tuple[str, str]:
    """Parse an ``owner/name`` string into ``(owner, name)``, lowercased.

    Raises :class:`ValueError` for malformed input.
    """

    cleaned = value.strip()
    if cleaned.startswith(("http://", "https://")):
        # Tolerate users pasting the URL.
        cleaned = cleaned.rsplit("github.com/", 1)[-1].rstrip("/")
        if cleaned.endswith(".git"):
            cleaned = cleaned[:-4]

    if not _REPO_PATTERN.match(cleaned):
        raise ValueError(
            "Expected `owner/repository` (e.g. `octocat/hello-world`)."
        )

    owner, name = cleaned.split("/", 1)
    return owner.lower(), name.lower()


def truncate(text: str, limit: int, suffix: str = "…") -> str:
    """Truncate ``text`` to at most ``limit`` characters (inclusive of suffix)."""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - len(suffix))] + suffix
