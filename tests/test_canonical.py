"""Mirror of `tests/canonical.test.ts`."""

from __future__ import annotations

from agent_ask.canonical import artifact_bytes_for_sig, compute_cid, jcs


def test_jcs_sorts_keys_no_whitespace() -> None:
    bs = jcs({"b": 2, "a": 1})
    assert bs.decode() == '{"a":1,"b":2}'


def test_jcs_identical_for_reordered_keys() -> None:
    a = jcs({"x": 1, "y": {"q": "z", "a": 1}})
    b = jcs({"y": {"a": 1, "q": "z"}, "x": 1})
    assert a == b


def test_artifact_bytes_for_sig_strips_sig() -> None:
    bs = artifact_bytes_for_sig({"a": 1, "sig": {"x": 1}, "b": 2})
    assert bs.decode() == '{"a":1,"b":2}'


def test_compute_cid_raw_sha256_bafk() -> None:
    cid = compute_cid(b"hello")
    assert cid.startswith("bafk")
    assert compute_cid(b"hello") == cid
    assert compute_cid(b"hellp") != cid
