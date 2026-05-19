"""Signed artifact schemas + build/verify (mirror of `src/artifact.ts`)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from .canonical import artifact_bytes_for_sig, compute_cid, jcs
from .identity import (
    Keypair,
    did_from_pubkey,
    from_base64,
    pubkey_from_did,
    sign,
    to_base64,
    verify,
)

PROTOCOL_VERSION = "agent-ask/0.1"

# SPEC §2.4: created_at MUST be RFC 3339 UTC second-precision with `Z` suffix.
_CANONICAL_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_DID_KEY_RE = re.compile(r"^did:key:")
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

Kind = Literal["question", "answer", "rating"]
# A raw signed artifact is just a JSON-shaped dict on the wire.
Artifact = dict[str, Any]


def _iso_seconds_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class VerifyResult:
    ok: bool
    errors: list[str]


# ---------------- Builders ----------------


def build_question(
    *,
    keypair: Keypair,
    title: str,
    body: str,
    tags: list[str],
    schema_ref: str | None = None,
    created_at: str | None = None,
    id: str | None = None,
) -> Artifact:
    base: Artifact = {
        "v": PROTOCOL_VERSION,
        "kind": "question",
        "id": id or str(uuid.uuid4()),
        "author_did": keypair.did,
        "created_at": created_at or _iso_seconds_now(),
        "title": title,
        "body": body,
        "tags": list(tags),
    }
    if schema_ref:
        base["schema_ref"] = schema_ref
    return _finalize(base, keypair)


def build_answer(
    *,
    keypair: Keypair,
    question_cid: str,
    body: str,
    refs: list[str] | None = None,
    created_at: str | None = None,
    id: str | None = None,
) -> Artifact:
    base: Artifact = {
        "v": PROTOCOL_VERSION,
        "kind": "answer",
        "id": id or str(uuid.uuid4()),
        "author_did": keypair.did,
        "created_at": created_at or _iso_seconds_now(),
        "question_cid": question_cid,
        "body": body,
    }
    if refs:
        base["refs"] = list(refs)
    return _finalize(base, keypair)


def build_rating(
    *,
    keypair: Keypair,
    target_cid: str,
    score: int,
    rationale: str | None = None,
    created_at: str | None = None,
    id: str | None = None,
) -> Artifact:
    if score not in (-1, 0, 1):
        raise ValueError(f"invalid rating score: {score}")
    base: Artifact = {
        "v": PROTOCOL_VERSION,
        "kind": "rating",
        "id": id or str(uuid.uuid4()),
        "author_did": keypair.did,
        "created_at": created_at or _iso_seconds_now(),
        "target_cid": target_cid,
        "score": score,
    }
    if rationale:
        base["rationale"] = rationale
    return _finalize(base, keypair)


def _finalize(base: Artifact, keypair: Keypair) -> Artifact:
    sig_bytes = sign(artifact_bytes_for_sig(base), keypair.private_key)
    base["sig"] = {
        "alg": "ed25519",
        "pubkey": to_base64(keypair.public_key),
        "sig": to_base64(sig_bytes),
    }
    return base


# ---------------- CID + verify ----------------


async def cid_of(artifact: Artifact) -> str:
    return compute_cid(jcs(artifact))


def cid_of_sync(artifact: Artifact) -> str:
    return compute_cid(jcs(artifact))


def _schema_errors(raw: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return ["schema: artifact must be an object"]

    def chk(cond: bool, msg: str) -> None:
        if not cond:
            errors.append(msg)

    chk(raw.get("v") == PROTOCOL_VERSION, f"schema: v must be {PROTOCOL_VERSION!r}")
    kind = raw.get("kind")
    chk(kind in ("question", "answer", "rating"), "schema: kind must be question|answer|rating")

    iid = raw.get("id")
    chk(isinstance(iid, str) and bool(_UUID_RE.match(iid)), "schema: id must be a UUID string")

    author = raw.get("author_did")
    chk(
        isinstance(author, str) and bool(_DID_KEY_RE.match(author)),
        "schema: author_did must start with did:key:",
    )

    created = raw.get("created_at")
    chk(
        isinstance(created, str) and bool(_CANONICAL_TIMESTAMP.match(created)),
        "schema: created_at must be UTC second-precision with Z suffix",
    )

    sig = raw.get("sig")
    if not (isinstance(sig, dict)
            and sig.get("alg") == "ed25519"
            and isinstance(sig.get("pubkey"), str)
            and isinstance(sig.get("sig"), str)):
        errors.append("schema: sig must be {alg=ed25519, pubkey, sig}")

    # Kind-specific
    if kind == "question":
        title = raw.get("title")
        chk(isinstance(title, str) and 1 <= len(title) <= 256, "schema: title 1..256 chars")
        chk(isinstance(raw.get("body"), str), "schema: body must be string")
        tags = raw.get("tags")
        chk(isinstance(tags, list) and all(isinstance(t, str) for t in tags),
            "schema: tags must be string[]")
        if "schema_ref" in raw:
            chk(isinstance(raw["schema_ref"], str) and bool(_URL_RE.match(raw["schema_ref"])),
                "schema: schema_ref must be a URL")
        _strict_keys(raw, {"v", "kind", "id", "author_did", "created_at", "title", "body",
                            "tags", "schema_ref", "sig"}, errors)
    elif kind == "answer":
        chk(isinstance(raw.get("question_cid"), str), "schema: question_cid must be string")
        chk(isinstance(raw.get("body"), str), "schema: body must be string")
        if "refs" in raw:
            refs = raw["refs"]
            chk(isinstance(refs, list) and all(isinstance(r, str) for r in refs),
                "schema: refs must be string[]")
        _strict_keys(raw, {"v", "kind", "id", "author_did", "created_at", "question_cid",
                            "body", "refs", "sig"}, errors)
    elif kind == "rating":
        chk(isinstance(raw.get("target_cid"), str), "schema: target_cid must be string")
        chk(raw.get("score") in (-1, 0, 1), "schema: score must be -1|0|1")
        if "rationale" in raw:
            chk(isinstance(raw["rationale"], str), "schema: rationale must be string")
        _strict_keys(raw, {"v", "kind", "id", "author_did", "created_at", "target_cid",
                            "score", "rationale", "sig"}, errors)

    return errors


def _strict_keys(d: dict[str, Any], allowed: set[str], errors: list[str]) -> None:
    extra = set(d.keys()) - allowed
    if extra:
        errors.append(f"schema: unexpected fields {sorted(extra)}")


async def verify_artifact(raw: Any) -> VerifyResult:
    errors = _schema_errors(raw)
    if errors:
        return VerifyResult(ok=False, errors=errors)
    artifact: Artifact = raw

    try:
        pubkey_from_sig = from_base64(artifact["sig"]["pubkey"])
        pubkey_from_author = pubkey_from_did(artifact["author_did"])
    except Exception as e:  # noqa: BLE001
        return VerifyResult(ok=False, errors=[f"identity: {e}"])

    if pubkey_from_sig != pubkey_from_author:
        errors.append("identity: sig.pubkey does not match author_did")
    if did_from_pubkey(pubkey_from_author) != artifact["author_did"]:
        errors.append("identity: author_did does not match did:key of pubkey")

    try:
        sig_bytes = from_base64(artifact["sig"]["sig"])
    except Exception as e:  # noqa: BLE001
        return VerifyResult(ok=False, errors=[f"identity: {e}"])
    signed_bytes = artifact_bytes_for_sig(artifact)
    if not verify(sig_bytes, signed_bytes, pubkey_from_author):
        errors.append("signature: invalid")

    return VerifyResult(ok=len(errors) == 0, errors=errors)
