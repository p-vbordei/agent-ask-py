"""RFC 8785 JCS canonical encoding + CIDv1 raw+sha256 helper.

Mirrors `src/canonical.ts` in the TS reference:
- `jcs(value)`        -> JCS-canonical bytes
- `artifact_bytes_for_sig(a)` -> JCS over the artifact minus `sig`
- `compute_cid(bytes)` -> CIDv1, raw codec (0x55), sha-256 multihash, base32 lower (multibase 'b')
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

import jcs as _jcs


def jcs(value: Any) -> bytes:
    return _jcs.canonicalize(value)


def artifact_bytes_for_sig(artifact: dict[str, Any]) -> bytes:
    rest = {k: v for k, v in artifact.items() if k != "sig"}
    return jcs(rest)


# Multicodec / multihash constants (unsigned varint, but all 1-byte here).
_CID_VERSION = 0x01
_CODEC_RAW = 0x55
_MULTIHASH_SHA256 = 0x12
_DIGEST_LEN = 0x20


def compute_cid(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    cid_bytes = bytes([_CID_VERSION, _CODEC_RAW, _MULTIHASH_SHA256, _DIGEST_LEN]) + digest
    b32 = base64.b32encode(cid_bytes).decode("ascii").lower().rstrip("=")
    return "b" + b32
