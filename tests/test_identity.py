"""Mirror of `tests/identity.test.ts`."""

from __future__ import annotations

import pytest

from agent_ask.identity import (
    did_from_pubkey,
    from_base64,
    generate_keypair,
    pubkey_from_did,
    sign,
    to_base64,
    verify,
)


def test_keypair_sizes_and_did_prefix() -> None:
    kp = generate_keypair()
    assert len(kp.private_key) == 32
    assert len(kp.public_key) == 32
    assert kp.did.startswith("did:key:z")


def test_did_key_roundtrips() -> None:
    kp = generate_keypair()
    recovered = pubkey_from_did(kp.did)
    assert recovered == kp.public_key


def test_sign_verify_roundtrip() -> None:
    kp = generate_keypair()
    msg = b"hello"
    sig = sign(msg, kp.private_key)
    assert len(sig) == 64
    assert verify(sig, msg, kp.public_key) is True


def test_verify_rejects_mutated_message() -> None:
    kp = generate_keypair()
    sig = sign(b"hello", kp.private_key)
    assert verify(sig, b"hellp", kp.public_key) is False


def test_base64_roundtrip() -> None:
    original = bytes([0, 1, 2, 255, 128, 64])
    assert from_base64(to_base64(original)) == original


def test_pubkey_from_did_rejects_wrong_multicodec() -> None:
    with pytest.raises(Exception):
        pubkey_from_did("did:key:zQ3sh")


def test_did_from_pubkey_deterministic() -> None:
    pk = bytes([7] * 32)
    assert did_from_pubkey(pk) == did_from_pubkey(pk)
