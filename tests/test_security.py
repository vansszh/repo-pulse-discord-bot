"""Tests for :mod:`repopulse.security`."""

from __future__ import annotations

from repopulse.security import compute_signature, verify_signature


def test_compute_and_verify_roundtrip() -> None:
    secret = "super-secret"
    payload = b'{"hello": "world"}'
    sig = compute_signature(secret, payload)
    assert sig.startswith("sha256=")
    assert verify_signature(secret, payload, sig) is True


def test_verify_rejects_wrong_secret() -> None:
    payload = b"x"
    sig = compute_signature("right", payload)
    assert verify_signature("wrong", payload, sig) is False


def test_verify_rejects_tampered_payload() -> None:
    secret = "s"
    sig = compute_signature(secret, b"original")
    assert verify_signature(secret, b"tampered", sig) is False


def test_verify_rejects_missing_header() -> None:
    assert verify_signature("s", b"x", None) is False
    assert verify_signature("s", b"x", "") is False


def test_verify_rejects_wrong_prefix() -> None:
    sig = compute_signature("s", b"x").replace("sha256=", "sha1=")
    assert verify_signature("s", b"x", sig) is False


def test_verify_rejects_empty_secret() -> None:
    # Defensive: when no secret is configured we must not accept anything.
    assert verify_signature("", b"x", "sha256=abcdef") is False


def test_compare_is_constant_time_safe() -> None:
    # We can't directly test timing, but we can confirm differently-shaped
    # signatures don't raise and still return False.
    assert verify_signature("s", b"x", "sha256=") is False
    assert verify_signature("s", b"x", "sha256=not-hex") is False
