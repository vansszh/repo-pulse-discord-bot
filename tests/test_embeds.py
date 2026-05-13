"""Tests for :mod:`repopulse.embeds`.

We synthesize minimal-but-realistic GitHub webhook payloads. Full schemas
are documented at https://docs.github.com/en/webhooks/webhook-events-and-payloads.
"""

from __future__ import annotations

import discord

from repopulse import embeds


def _base_repo() -> dict:
    return {
        "full_name": "octocat/hello-world",
        "name": "hello-world",
        "owner": {"login": "octocat"},
    }


def _sender() -> dict:
    return {
        "login": "octocat",
        "html_url": "https://github.com/octocat",
        "avatar_url": "https://avatars.githubusercontent.com/u/1?v=4",
    }


# -- Issues --------------------------------------------------------------------


def test_issue_opened_builds_green_embed() -> None:
    payload = {
        "action": "opened",
        "issue": {
            "number": 42,
            "title": "Something is broken",
            "html_url": "https://github.com/octocat/hello-world/issues/42",
            "body": "Details here",
            "labels": [{"name": "bug"}, {"name": "help wanted"}],
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        },
        "repository": _base_repo(),
        "sender": _sender(),
    }
    embed = embeds.build_issue_embed(payload)
    assert embed is not None
    assert "Issue opened" in (embed.title or "")
    assert "#42" in (embed.title or "")
    assert embed.color == embeds.COLOR_OPEN
    label_field = next((f for f in embed.fields if f.name == "Labels"), None)
    assert label_field is not None
    assert "`bug`" in (label_field.value or "")


def test_issue_closed_completed_uses_merged_color() -> None:
    payload = {
        "action": "closed",
        "issue": {
            "number": 1,
            "title": "Done",
            "html_url": "https://x",
            "state_reason": "completed",
            "labels": [],
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        },
        "repository": _base_repo(),
        "sender": _sender(),
    }
    embed = embeds.build_issue_embed(payload)
    assert embed is not None
    assert embed.color == embeds.COLOR_MERGED


def test_issue_unknown_action_is_ignored() -> None:
    payload = {"action": "edited", "issue": {}, "repository": _base_repo(), "sender": _sender()}
    assert embeds.build_issue_embed(payload) is None


# -- Pull requests -------------------------------------------------------------


def _pr(**overrides) -> dict:
    pr = {
        "number": 7,
        "title": "Add feature",
        "html_url": "https://github.com/octocat/hello-world/pull/7",
        "body": "This adds a feature.",
        "draft": False,
        "merged": False,
        "state": "open",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "head": {"ref": "feature"},
        "base": {"ref": "main"},
        "changed_files": 3,
        "additions": 42,
        "deletions": 7,
        "labels": [],
        "user": {"login": "octocat"},
    }
    pr.update(overrides)
    return pr


def test_pr_opened_is_green() -> None:
    payload = {
        "action": "opened",
        "pull_request": _pr(),
        "repository": _base_repo(),
        "sender": _sender(),
    }
    embed = embeds.build_pull_request_embed(payload)
    assert embed is not None
    assert embed.color == embeds.COLOR_OPEN
    assert "Pull request opened" in (embed.title or "")


def test_pr_draft_uses_gray() -> None:
    payload = {
        "action": "opened",
        "pull_request": _pr(draft=True),
        "repository": _base_repo(),
        "sender": _sender(),
    }
    embed = embeds.build_pull_request_embed(payload)
    assert embed is not None
    assert embed.color == embeds.COLOR_DRAFT


def test_pr_merged_is_purple() -> None:
    payload = {
        "action": "closed",
        "pull_request": _pr(merged=True, state="closed"),
        "repository": _base_repo(),
        "sender": _sender(),
    }
    embed = embeds.build_pull_request_embed(payload)
    assert embed is not None
    assert embed.color == embeds.COLOR_MERGED


def test_pr_closed_without_merge_is_red() -> None:
    payload = {
        "action": "closed",
        "pull_request": _pr(merged=False, state="closed"),
        "repository": _base_repo(),
        "sender": _sender(),
    }
    embed = embeds.build_pull_request_embed(payload)
    assert embed is not None
    assert embed.color == embeds.COLOR_CLOSED


# -- Reviews -------------------------------------------------------------------


def test_review_approved_is_green() -> None:
    payload = {
        "action": "submitted",
        "review": {
            "state": "approved",
            "body": "LGTM",
            "submitted_at": "2024-01-01T00:00:00Z",
            "html_url": "https://x",
        },
        "pull_request": _pr(),
        "repository": _base_repo(),
        "sender": _sender(),
    }
    embed = embeds.build_review_embed(payload)
    assert embed is not None
    assert embed.color == embeds.COLOR_OPEN


def test_review_changes_requested_is_warning() -> None:
    payload = {
        "action": "submitted",
        "review": {"state": "changes_requested", "body": "fix this", "submitted_at": "2024-01-01T00:00:00Z"},
        "pull_request": _pr(),
        "repository": _base_repo(),
        "sender": _sender(),
    }
    embed = embeds.build_review_embed(payload)
    assert embed is not None
    assert embed.color == embeds.COLOR_WARNING


def test_empty_commented_review_ignored() -> None:
    payload = {
        "action": "submitted",
        "review": {"state": "commented", "body": "", "submitted_at": "2024-01-01T00:00:00Z"},
        "pull_request": _pr(),
        "repository": _base_repo(),
        "sender": _sender(),
    }
    assert embeds.build_review_embed(payload) is None


# -- Push ----------------------------------------------------------------------


def test_push_builds_description_from_commits() -> None:
    payload = {
        "ref": "refs/heads/main",
        "created": False,
        "deleted": False,
        "forced": False,
        "compare": "https://github.com/octocat/hello-world/compare/a...b",
        "commits": [
            {
                "id": "abcdef1234567890",
                "message": "fix: bug",
                "author": {"name": "octocat"},
                "url": "https://x/commit/abcdef1",
            }
        ],
        "repository": _base_repo(),
        "sender": _sender(),
    }
    embed = embeds.build_push_embed(payload)
    assert embed is not None
    assert "`main`" in (embed.title or "")
    assert "abcdef1" in (embed.description or "")


def test_push_with_no_commits_and_no_branch_lifecycle_is_ignored() -> None:
    payload = {
        "ref": "refs/heads/main",
        "created": False,
        "deleted": False,
        "forced": False,
        "commits": [],
        "repository": _base_repo(),
        "sender": _sender(),
    }
    assert embeds.build_push_embed(payload) is None


def test_force_push_is_flagged_warning() -> None:
    payload = {
        "ref": "refs/heads/main",
        "forced": True,
        "created": False,
        "deleted": False,
        "commits": [{"id": "a" * 40, "message": "x", "author": {"name": "o"}, "url": "u"}],
        "repository": _base_repo(),
        "sender": _sender(),
    }
    embed = embeds.build_push_embed(payload)
    assert embed is not None
    assert embed.color == embeds.COLOR_WARNING


# -- Release -------------------------------------------------------------------


def test_release_published_is_merged_color() -> None:
    payload = {
        "action": "published",
        "release": {
            "tag_name": "v1.0.0",
            "name": "First stable",
            "html_url": "https://x",
            "body": "notes",
            "published_at": "2024-01-01T00:00:00Z",
            "prerelease": False,
        },
        "repository": _base_repo(),
        "sender": _sender(),
    }
    embed = embeds.build_release_embed(payload)
    assert embed is not None
    assert embed.color == embeds.COLOR_MERGED


def test_prerelease_is_warning() -> None:
    payload = {
        "action": "published",
        "release": {
            "tag_name": "v1.0.0-rc1",
            "name": "RC",
            "html_url": "https://x",
            "body": "",
            "published_at": "2024-01-01T00:00:00Z",
            "prerelease": True,
        },
        "repository": _base_repo(),
        "sender": _sender(),
    }
    embed = embeds.build_release_embed(payload)
    assert embed is not None
    assert embed.color == embeds.COLOR_WARNING


# -- Workflow run --------------------------------------------------------------


def test_workflow_success_is_green() -> None:
    payload = {
        "action": "completed",
        "workflow_run": {
            "name": "CI",
            "conclusion": "success",
            "head_branch": "main",
            "html_url": "https://x",
            "updated_at": "2024-01-01T00:00:00Z",
            "event": "push",
            "head_commit": {"message": "fix: bug\n\ndetails"},
        },
        "repository": _base_repo(),
        "sender": _sender(),
    }
    embed = embeds.build_workflow_run_embed(payload)
    assert embed is not None
    assert embed.color == embeds.COLOR_SUCCESS
    commit_field = next((f for f in embed.fields if f.name == "Commit"), None)
    assert commit_field is not None
    assert "fix: bug" in (commit_field.value or "")


def test_workflow_failure_is_red() -> None:
    payload = {
        "action": "completed",
        "workflow_run": {
            "name": "CI",
            "conclusion": "failure",
            "head_branch": "main",
            "html_url": "https://x",
            "updated_at": "2024-01-01T00:00:00Z",
        },
        "repository": _base_repo(),
        "sender": _sender(),
    }
    embed = embeds.build_workflow_run_embed(payload)
    assert embed is not None
    assert embed.color == embeds.COLOR_FAILURE


# -- Reminder ------------------------------------------------------------------


def test_review_reminder_embed_is_warning_colored() -> None:
    embed = embeds.build_review_reminder_embed(
        owner="octocat",
        name="hello-world",
        number=10,
        title="Needs attention",
        url="https://x",
        author="alice",
        hours=24,
    )
    assert embed.color == embeds.COLOR_WARNING
    assert "#10" in (embed.title or "")
    assert isinstance(embed, discord.Embed)
