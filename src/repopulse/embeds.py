"""Discord embed builders for GitHub webhook events.

Every builder takes the parsed JSON body of a GitHub webhook and returns a
:class:`discord.Embed`, or ``None`` if the event variant should be ignored.

Design goals:

* Stay under Discord's embed limits (title ≤ 256, description ≤ 4096,
  field ≤ 1024, total ≤ 6000).
* Use GitHub-like colors so a glance tells you what happened.
* Link the title directly to the GitHub URL.
* Show the author's avatar.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import discord

from .utils import truncate

# ---------------------------------------------------------------------------
# Colors (GitHub-like palette)
# ---------------------------------------------------------------------------

COLOR_OPEN = discord.Color.from_str("#2ea043")       # green
COLOR_MERGED = discord.Color.from_str("#8957e5")     # purple
COLOR_CLOSED = discord.Color.from_str("#cf222e")     # red
COLOR_DRAFT = discord.Color.from_str("#6e7681")      # gray
COLOR_COMMENT = discord.Color.from_str("#0969da")    # blue
COLOR_WARNING = discord.Color.from_str("#bf8700")    # amber
COLOR_NEUTRAL = discord.Color.from_str("#57606a")    # slate
COLOR_SUCCESS = COLOR_OPEN
COLOR_FAILURE = COLOR_CLOSED


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _parse_ts(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(UTC)
    try:
        # GitHub timestamps are ISO 8601, often ending in "Z".
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)


def _author(payload: dict[str, Any]) -> tuple[str, str | None, str | None]:
    """Return ``(name, url, avatar_url)`` for the sender/user of an event."""
    user = payload.get("sender") or payload.get("pusher") or {}
    name = user.get("login") or user.get("name") or "unknown"
    return name, user.get("html_url"), user.get("avatar_url")


def _repo_footer(repo: dict[str, Any]) -> str:
    full = repo.get("full_name") or f"{repo.get('owner', {}).get('login', '?')}/{repo.get('name', '?')}"
    return full


def _labels_value(labels: list[dict[str, Any]] | None) -> str | None:
    if not labels:
        return None
    names = [f"`{lbl.get('name', '')}`" for lbl in labels if lbl.get("name")]
    if not names:
        return None
    return truncate(", ".join(names), 1024)


def _base_embed(
    *,
    title: str,
    url: str | None,
    color: discord.Color,
    payload: dict[str, Any],
    timestamp: datetime | None = None,
    description: str | None = None,
) -> discord.Embed:
    name, user_url, avatar = _author(payload)
    embed = discord.Embed(
        title=truncate(title, 256),
        url=url,
        color=color,
        timestamp=timestamp or datetime.now(UTC),
        description=truncate(description, 4000) if description else None,
    )
    embed.set_author(name=name, url=user_url, icon_url=avatar)
    repo = payload.get("repository") or {}
    embed.set_footer(text=_repo_footer(repo))
    return embed


# ---------------------------------------------------------------------------
# Event builders
# ---------------------------------------------------------------------------


def build_issue_embed(payload: dict[str, Any]) -> discord.Embed | None:
    """Build an embed for ``issues`` events (opened / closed / reopened)."""
    action = payload.get("action")
    if action not in {"opened", "closed", "reopened"}:
        return None

    issue = payload.get("issue") or {}
    number = issue.get("number")
    title = issue.get("title", "(no title)")
    url = issue.get("html_url")
    body = issue.get("body") or ""

    if action == "opened":
        verb = "📥 Issue opened"
        color = COLOR_OPEN
    elif action == "reopened":
        verb = "🔄 Issue reopened"
        color = COLOR_OPEN
    else:  # closed
        state_reason = issue.get("state_reason")
        if state_reason == "completed":
            verb = "✅ Issue closed (completed)"
            color = COLOR_MERGED
        else:
            verb = "🚫 Issue closed"
            color = COLOR_NEUTRAL

    embed = _base_embed(
        title=f"{verb} · #{number} {title}",
        url=url,
        color=color,
        payload=payload,
        timestamp=_parse_ts(issue.get("updated_at") or issue.get("created_at")),
        description=body if action == "opened" else None,
    )

    labels_val = _labels_value(issue.get("labels"))
    if labels_val:
        embed.add_field(name="Labels", value=labels_val, inline=False)

    return embed


def build_pull_request_embed(payload: dict[str, Any]) -> discord.Embed | None:
    """Build an embed for ``pull_request`` events."""
    action = payload.get("action")
    interesting = {"opened", "closed", "reopened", "ready_for_review", "review_requested"}
    if action not in interesting:
        return None

    pr = payload.get("pull_request") or {}
    number = pr.get("number")
    title = pr.get("title", "(no title)")
    url = pr.get("html_url")
    body = pr.get("body") or ""
    merged = bool(pr.get("merged"))
    draft = bool(pr.get("draft"))

    if action == "opened":
        if draft:
            verb, color = "📝 Draft pull request opened", COLOR_DRAFT
        else:
            verb, color = "🔀 Pull request opened", COLOR_OPEN
    elif action == "reopened":
        verb, color = "🔄 Pull request reopened", COLOR_OPEN
    elif action == "ready_for_review":
        verb, color = "🚀 Pull request ready for review", COLOR_OPEN
    elif action == "review_requested":
        reviewer = (payload.get("requested_reviewer") or {}).get("login")
        verb = f"👀 Review requested from {reviewer}" if reviewer else "👀 Review requested"
        color = COLOR_COMMENT
    elif action == "closed":
        if merged:
            verb, color = "🟣 Pull request merged", COLOR_MERGED
        else:
            verb, color = "🔴 Pull request closed", COLOR_CLOSED
    else:
        return None

    embed = _base_embed(
        title=f"{verb} · #{number} {title}",
        url=url,
        color=color,
        payload=payload,
        timestamp=_parse_ts(pr.get("updated_at") or pr.get("created_at")),
        description=body if action == "opened" else None,
    )

    # Branch info
    head = (pr.get("head") or {}).get("ref")
    base = (pr.get("base") or {}).get("ref")
    if head and base:
        embed.add_field(name="Branch", value=f"`{head}` → `{base}`", inline=True)

    # File / line stats
    changed = pr.get("changed_files")
    additions = pr.get("additions")
    deletions = pr.get("deletions")
    if changed is not None:
        embed.add_field(
            name="Changes",
            value=f"{changed} file(s) · +{additions or 0} / -{deletions or 0}",
            inline=True,
        )

    labels_val = _labels_value(pr.get("labels"))
    if labels_val:
        embed.add_field(name="Labels", value=labels_val, inline=False)

    return embed


def build_review_embed(payload: dict[str, Any]) -> discord.Embed | None:
    """Build an embed for ``pull_request_review`` events (action=submitted)."""
    if payload.get("action") != "submitted":
        return None

    review = payload.get("review") or {}
    pr = payload.get("pull_request") or {}
    state = (review.get("state") or "").lower()
    number = pr.get("number")
    pr_title = pr.get("title", "(no title)")
    body = review.get("body") or ""
    url = review.get("html_url") or pr.get("html_url")

    if state == "approved":
        verb, color = "✅ Review approved", COLOR_OPEN
    elif state == "changes_requested":
        verb, color = "⚠️ Changes requested", COLOR_WARNING
    elif state == "commented":
        if not body.strip():
            # Empty "commented" reviews are usually noise.
            return None
        verb, color = "💬 Review commented", COLOR_COMMENT
    else:
        return None

    embed = _base_embed(
        title=f"{verb} on #{number} {pr_title}",
        url=url,
        color=color,
        payload=payload,
        timestamp=_parse_ts(review.get("submitted_at")),
        description=body or None,
    )
    return embed


def build_push_embed(payload: dict[str, Any]) -> discord.Embed | None:
    """Build an embed for ``push`` events."""
    commits = payload.get("commits") or []
    ref = payload.get("ref", "")
    branch = ref.rsplit("/", 1)[-1] if ref else "?"
    forced = bool(payload.get("forced"))
    created = bool(payload.get("created"))
    deleted = bool(payload.get("deleted"))
    compare_url = payload.get("compare")

    # Skip no-op pushes (e.g. tag deletes with no commits) unless they
    # represent branch lifecycle events.
    if not commits and not (created or deleted):
        return None

    if deleted:
        verb, color = f"🗑️ Branch `{branch}` deleted", COLOR_CLOSED
    elif created:
        verb, color = f"🌱 Branch `{branch}` created", COLOR_OPEN
    elif forced:
        verb, color = f"⚠️ Force push to `{branch}`", COLOR_WARNING
    else:
        count = len(commits)
        verb = f"📦 {count} commit{'s' if count != 1 else ''} pushed to `{branch}`"
        color = COLOR_COMMENT

    lines: list[str] = []
    for commit in commits[:10]:
        sha = (commit.get("id") or "")[:7]
        msg = (commit.get("message") or "").splitlines()[0] if commit.get("message") else ""
        author = (commit.get("author") or {}).get("name") or "unknown"
        url = commit.get("url")
        lines.append(f"[`{sha}`]({url}) {truncate(msg, 80)} — *{author}*")
    if len(commits) > 10:
        lines.append(f"… and {len(commits) - 10} more")

    embed = _base_embed(
        title=verb,
        url=compare_url,
        color=color,
        payload=payload,
        description="\n".join(lines) if lines else None,
    )
    return embed


def build_release_embed(payload: dict[str, Any]) -> discord.Embed | None:
    """Build an embed for ``release`` events (action=published)."""
    if payload.get("action") != "published":
        return None

    release = payload.get("release") or {}
    tag = release.get("tag_name", "?")
    name = release.get("name") or tag
    url = release.get("html_url")
    body = release.get("body") or ""
    prerelease = bool(release.get("prerelease"))

    if prerelease:
        verb, color = f"🧪 Pre-release `{tag}` published", COLOR_WARNING
    else:
        verb, color = f"🎉 Release `{tag}` published", COLOR_MERGED

    embed = _base_embed(
        title=f"{verb} — {name}",
        url=url,
        color=color,
        payload=payload,
        timestamp=_parse_ts(release.get("published_at") or release.get("created_at")),
        description=body or None,
    )
    return embed


def build_workflow_run_embed(payload: dict[str, Any]) -> discord.Embed | None:
    """Build an embed for ``workflow_run`` events (action=completed)."""
    if payload.get("action") != "completed":
        return None

    run = payload.get("workflow_run") or {}
    conclusion = (run.get("conclusion") or "").lower()
    name = run.get("name") or "workflow"
    branch = run.get("head_branch") or "?"
    url = run.get("html_url")

    status_icons = {
        "success": ("✅", COLOR_SUCCESS),
        "failure": ("❌", COLOR_FAILURE),
        "cancelled": ("⚪", COLOR_NEUTRAL),
        "timed_out": ("⏱️", COLOR_FAILURE),
        "action_required": ("⚠️", COLOR_WARNING),
        "neutral": ("➖", COLOR_NEUTRAL),
        "skipped": ("⏭️", COLOR_NEUTRAL),
        "stale": ("💤", COLOR_NEUTRAL),
    }
    icon, color = status_icons.get(conclusion, ("🏁", COLOR_NEUTRAL))

    embed = _base_embed(
        title=f"{icon} Workflow '{name}' {conclusion or 'completed'} on `{branch}`",
        url=url,
        color=color,
        payload=payload,
        timestamp=_parse_ts(run.get("updated_at") or run.get("run_started_at")),
    )

    head_commit = run.get("head_commit") or {}
    msg = (head_commit.get("message") or "").splitlines()[0] if head_commit.get("message") else ""
    if msg:
        embed.add_field(name="Commit", value=truncate(msg, 1024), inline=False)

    event_trigger = run.get("event")
    if event_trigger:
        embed.add_field(name="Trigger", value=f"`{event_trigger}`", inline=True)

    return embed


def build_review_reminder_embed(
    *, owner: str, name: str, number: int, title: str, url: str, author: str, hours: int
) -> discord.Embed:
    """Built by the background task, not a webhook handler — kept here for symmetry."""
    embed = discord.Embed(
        title=truncate(f"⏰ Reminder: PR #{number} needs review — {title}", 256),
        url=url,
        color=COLOR_WARNING,
        timestamp=datetime.now(UTC),
        description=(
            f"This pull request has been open for more than **{hours} hours** "
            f"without a review. Author: **{author}**."
        ),
    )
    embed.set_footer(text=f"{owner}/{name}")
    return embed
