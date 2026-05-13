from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import discord

from .utils import truncate

# GitHub-like palette.
COLOR_OPEN = discord.Color.from_str("#2ea043")
COLOR_MERGED = discord.Color.from_str("#8957e5")
COLOR_CLOSED = discord.Color.from_str("#cf222e")
COLOR_DRAFT = discord.Color.from_str("#6e7681")
COLOR_COMMENT = discord.Color.from_str("#0969da")
COLOR_WARNING = discord.Color.from_str("#bf8700")
COLOR_NEUTRAL = discord.Color.from_str("#57606a")
COLOR_SUCCESS = COLOR_OPEN
COLOR_FAILURE = COLOR_CLOSED


def _parse_ts(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(UTC)
    try:
        # GitHub timestamps are ISO 8601, usually ending in "Z".
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)


def _author(payload: dict[str, Any]) -> tuple[str, str | None, str | None]:
    user = payload.get("sender") or payload.get("pusher") or {}
    name = user.get("login") or user.get("name") or "unknown"
    return name, user.get("html_url"), user.get("avatar_url")


def _repo_footer(repo: dict[str, Any]) -> str:
    return repo.get("full_name") or f"{repo.get('owner', {}).get('login', '?')}/{repo.get('name', '?')}"


def _labels_value(labels: list[dict[str, Any]] | None) -> str | None:
    if not labels:
        return None
    names = [f"`{lbl.get('name', '')}`" for lbl in labels if lbl.get("name")]
    return truncate(", ".join(names), 1024) if names else None


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
    embed.set_footer(text=_repo_footer(payload.get("repository") or {}))
    return embed


def build_issue_embed(payload: dict[str, Any]) -> discord.Embed | None:
    action = payload.get("action")
    if action not in {"opened", "closed", "reopened"}:
        return None

    issue = payload.get("issue") or {}
    number = issue.get("number")
    title = issue.get("title", "(no title)")
    url = issue.get("html_url")
    body = issue.get("body") or ""

    if action == "opened":
        verb, color = "📥 Issue opened", COLOR_OPEN
    elif action == "reopened":
        verb, color = "🔄 Issue reopened", COLOR_OPEN
    else:
        if issue.get("state_reason") == "completed":
            verb, color = "✅ Issue closed (completed)", COLOR_MERGED
        else:
            verb, color = "🚫 Issue closed", COLOR_NEUTRAL

    embed = _base_embed(
        title=f"{verb} · #{number} {title}",
        url=url,
        color=color,
        payload=payload,
        timestamp=_parse_ts(issue.get("updated_at") or issue.get("created_at")),
        description=body if action == "opened" else None,
    )

    labels = _labels_value(issue.get("labels"))
    if labels:
        embed.add_field(name="Labels", value=labels, inline=False)
    return embed


def build_pull_request_embed(payload: dict[str, Any]) -> discord.Embed | None:
    action = payload.get("action")
    if action not in {"opened", "closed", "reopened", "ready_for_review", "review_requested"}:
        return None

    pr = payload.get("pull_request") or {}
    number = pr.get("number")
    title = pr.get("title", "(no title)")
    url = pr.get("html_url")
    body = pr.get("body") or ""
    merged = bool(pr.get("merged"))
    draft = bool(pr.get("draft"))

    if action == "opened":
        verb, color = ("📝 Draft pull request opened", COLOR_DRAFT) if draft else ("🔀 Pull request opened", COLOR_OPEN)
    elif action == "reopened":
        verb, color = "🔄 Pull request reopened", COLOR_OPEN
    elif action == "ready_for_review":
        verb, color = "🚀 Pull request ready for review", COLOR_OPEN
    elif action == "review_requested":
        reviewer = (payload.get("requested_reviewer") or {}).get("login")
        verb = f"👀 Review requested from {reviewer}" if reviewer else "👀 Review requested"
        color = COLOR_COMMENT
    elif action == "closed":
        verb, color = ("🟣 Pull request merged", COLOR_MERGED) if merged else ("🔴 Pull request closed", COLOR_CLOSED)
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

    head = (pr.get("head") or {}).get("ref")
    base = (pr.get("base") or {}).get("ref")
    if head and base:
        embed.add_field(name="Branch", value=f"`{head}` → `{base}`", inline=True)

    changed = pr.get("changed_files")
    if changed is not None:
        embed.add_field(
            name="Changes",
            value=f"{changed} file(s) · +{pr.get('additions') or 0} / -{pr.get('deletions') or 0}",
            inline=True,
        )

    labels = _labels_value(pr.get("labels"))
    if labels:
        embed.add_field(name="Labels", value=labels, inline=False)
    return embed


def build_review_embed(payload: dict[str, Any]) -> discord.Embed | None:
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
            # Empty "commented" reviews are usually just noise.
            return None
        verb, color = "💬 Review commented", COLOR_COMMENT
    else:
        return None

    return _base_embed(
        title=f"{verb} on #{number} {pr_title}",
        url=url,
        color=color,
        payload=payload,
        timestamp=_parse_ts(review.get("submitted_at")),
        description=body or None,
    )


def build_push_embed(payload: dict[str, Any]) -> discord.Embed | None:
    commits = payload.get("commits") or []
    ref = payload.get("ref", "")
    branch = ref.rsplit("/", 1)[-1] if ref else "?"
    forced = bool(payload.get("forced"))
    created = bool(payload.get("created"))
    deleted = bool(payload.get("deleted"))
    compare_url = payload.get("compare")

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
        lines.append(f"[`{sha}`]({commit.get('url')}) {truncate(msg, 80)} — *{author}*")
    if len(commits) > 10:
        lines.append(f"… and {len(commits) - 10} more")

    return _base_embed(
        title=verb,
        url=compare_url,
        color=color,
        payload=payload,
        description="\n".join(lines) if lines else None,
    )


def build_release_embed(payload: dict[str, Any]) -> discord.Embed | None:
    if payload.get("action") != "published":
        return None

    release = payload.get("release") or {}
    tag = release.get("tag_name", "?")
    name = release.get("name") or tag
    url = release.get("html_url")
    body = release.get("body") or ""

    if release.get("prerelease"):
        verb, color = f"🧪 Pre-release `{tag}` published", COLOR_WARNING
    else:
        verb, color = f"🎉 Release `{tag}` published", COLOR_MERGED

    return _base_embed(
        title=f"{verb} — {name}",
        url=url,
        color=color,
        payload=payload,
        timestamp=_parse_ts(release.get("published_at") or release.get("created_at")),
        description=body or None,
    )


def build_workflow_run_embed(payload: dict[str, Any]) -> discord.Embed | None:
    if payload.get("action") != "completed":
        return None

    run = payload.get("workflow_run") or {}
    conclusion = (run.get("conclusion") or "").lower()
    name = run.get("name") or "workflow"
    branch = run.get("head_branch") or "?"
    url = run.get("html_url")

    icons = {
        "success": ("✅", COLOR_SUCCESS),
        "failure": ("❌", COLOR_FAILURE),
        "cancelled": ("⚪", COLOR_NEUTRAL),
        "timed_out": ("⏱️", COLOR_FAILURE),
        "action_required": ("⚠️", COLOR_WARNING),
        "neutral": ("➖", COLOR_NEUTRAL),
        "skipped": ("⏭️", COLOR_NEUTRAL),
        "stale": ("💤", COLOR_NEUTRAL),
    }
    icon, color = icons.get(conclusion, ("🏁", COLOR_NEUTRAL))

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

    if run.get("event"):
        embed.add_field(name="Trigger", value=f"`{run['event']}`", inline=True)
    return embed


def build_review_reminder_embed(
    *, owner: str, name: str, number: int, title: str, url: str, author: str, hours: int
) -> discord.Embed:
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
