from __future__ import annotations

import pytest

from repopulse.utils import parse_repo, truncate


class TestParseRepo:
    def test_basic(self) -> None:
        assert parse_repo("octocat/Hello-World") == ("octocat", "hello-world")

    def test_lowercases_owner_and_name(self) -> None:
        assert parse_repo("VANSSZH/Repo-Pulse") == ("vansszh", "repo-pulse")

    def test_strips_whitespace(self) -> None:
        assert parse_repo("  octocat/hello-world  ") == ("octocat", "hello-world")

    def test_accepts_https_url(self) -> None:
        assert parse_repo("https://github.com/octocat/Hello-World") == ("octocat", "hello-world")

    def test_accepts_https_url_with_git_suffix(self) -> None:
        assert parse_repo("https://github.com/octocat/Hello-World.git") == ("octocat", "hello-world")

    def test_accepts_dots_in_name(self) -> None:
        assert parse_repo("github/docs.github.com") == ("github", "docs.github.com")

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "no-slash",
            "too/many/slashes",
            "/missing-owner",
            "missing-name/",
            "bad owner/name",
            "owner/ba d name",
        ],
    )
    def test_rejects_malformed(self, value: str) -> None:
        with pytest.raises(ValueError):
            parse_repo(value)


class TestTruncate:
    def test_no_truncation_needed(self) -> None:
        assert truncate("hello", 10) == "hello"

    def test_truncates_with_suffix(self) -> None:
        out = truncate("abcdefghij", 5)
        assert len(out) == 5
        assert out.endswith("…")

    def test_limit_smaller_than_suffix(self) -> None:
        # Just shouldn't raise; returns whatever fits.
        assert truncate("abc", 0) in ("", "…")
