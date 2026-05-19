"""Ed25519 keypair + did:key helpers (mirror of `src/identity.ts`)."""

from __future__ import annotations

import base64
from dataclasses import dataclass

import base58
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature

_ED25519_MULTICODEC = bytes([0xED, 0x01])


@dataclass(frozen=True)
class Keypair:
    private_key: bytes
    public_key: bytes
    did: str


def generate_keypair() -> Keypair:
    sk = Ed25519PrivateKey.generate()
    priv = sk.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub = sk.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return Keypair(private_key=priv, public_key=pub, did=did_from_pubkey(pub))


def did_from_pubkey(pubkey: bytes) -> str:
    if len(pubkey) != 32:
        raise ValueError("pubkey must be 32 bytes")
    payload = _ED25519_MULTICODEC + pubkey
    return "did:key:z" + base58.b58encode(payload).decode("ascii")


def pubkey_from_did(did: str) -> bytes:
    if not did.startswith("did:key:"):
        raise ValueError("not a did:key")
    multibase = did[len("did:key:") :]
    if not multibase.startswith("z"):
        raise ValueError("did:key must use base58btc (z-prefix)")
    decoded = base58.b58decode(multibase[1:])
    if len(decoded) != 34 or decoded[0] != 0xED or decoded[1] != 0x01:
        raise ValueError("did:key multicodec is not ed25519-pub")
    return bytes(decoded[2:])


def sign(message: bytes, private_key: bytes) -> bytes:
    sk = Ed25519PrivateKey.from_private_bytes(private_key)
    return sk.sign(message)


def verify(sig: bytes, message: bytes, public_key: bytes) -> bool:
    try:
        pk = Ed25519PublicKey.from_public_bytes(public_key)
        pk.verify(sig, message)
        return True
    except (InvalidSignature, ValueError, Exception):
        return False


def to_base64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def from_base64(s: str) -> bytes:
    return base64.b64decode(s, validate=False)
