from __future__ import annotations

import re

# owner: alphanumeric + hyphens, 1-39 chars.  name: alphanum + . _ -, 1-100 chars.
_REPO_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")


def parse_repo(value: str) -> tuple[str, str]:
    """`owner/name` → (`owner`, `name`), lowercased. Also accepts github.com URLs."""
    s = value.strip()
    if s.startswith(("http://", "https://")):
        s = s.rsplit("github.com/", 1)[-1].rstrip("/")
        if s.endswith(".git"):
            s = s[:-4]

    if not _REPO_PATTERN.match(s):
        raise ValueError("Expected `owner/repository` (e.g. `octocat/hello-world`).")

    owner, name = s.split("/", 1)
    return owner.lower(), name.lower()


def truncate(text: str, limit: int, suffix: str = "…") -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - len(suffix))] + suffix
