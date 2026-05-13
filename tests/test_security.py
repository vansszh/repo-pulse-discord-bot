from __future__ import annotations

from repopulse.security import compute_signature, verify_signature


def test_compute_and_verify_roundtrip() -> None:
    secret = "super-secret"
    payload = b'{"hello": "world"}'
    sig = compute_signature(secret, payload)
    assert sig.startswith("sha256=")
    assert verify_signature(secret, payload, sig) is True


def test_verify_rejects_wrong_secret() -> None:
    sig = compute_signature("right", b"x")
    assert verify_signature("wrong", b"x", sig) is False


def test_verify_rejects_tampered_payload() -> None:
    sig = compute_signature("s", b"original")
    assert verify_signature("s", b"tampered", sig) is False


def test_verify_rejects_missing_header() -> None:
    assert verify_signature("s", b"x", None) is False
    assert verify_signature("s", b"x", "") is False


def test_verify_rejects_wrong_prefix() -> None:
    sig = compute_signature("s", b"x").replace("sha256=", "sha1=")
    assert verify_signature("s", b"x", sig) is False


def test_verify_rejects_empty_secret() -> None:
    assert verify_signature("", b"x", "sha256=abcdef") is False


def test_malformed_signatures_do_not_raise() -> None:
    assert verify_signature("s", b"x", "sha256=") is False
    assert verify_signature("s", b"x", "sha256=not-hex") is False
