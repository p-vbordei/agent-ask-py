"""Mirror of `tests/artifact.test.ts`."""

from __future__ import annotations

import pytest

from agent_ask.artifact import (
    build_answer,
    build_question,
    build_rating,
    cid_of,
    verify_artifact,
)
from agent_ask.identity import generate_keypair


async def test_build_question_returns_signed_artifact_no_cid_field() -> None:
    kp = generate_keypair()
    artifact = build_question(
        keypair=kp, title="hello world", body="does this protocol work?", tags=["meta"]
    )
    assert artifact["v"] == "agent-ask/0.1"
    assert artifact["kind"] == "question"
    assert artifact["title"] == "hello world"
    assert artifact["tags"] == ["meta"]
    assert artifact["author_did"] == kp.did
    assert artifact["sig"]["alg"] == "ed25519"
    assert isinstance(artifact["sig"]["sig"], str)
    assert "cid" not in artifact


async def test_cid_of_returns_bafk() -> None:
    kp = generate_keypair()
    artifact = build_question(keypair=kp, title="t", body="b", tags=[])
    cid = await cid_of(artifact)
    assert cid.startswith("bafk")


async def test_verify_accepts_freshly_built() -> None:
    kp = generate_keypair()
    artifact = build_question(keypair=kp, title="t", body="b", tags=[])
    result = await verify_artifact(artifact)
    assert result.ok
    assert result.errors == []


async def test_verify_rejects_mutated_body() -> None:
    kp = generate_keypair()
    artifact = build_question(keypair=kp, title="t", body="b", tags=[])
    tampered = {**artifact, "body": "b!"}
    result = await verify_artifact(tampered)
    assert not result.ok
    assert any("signature" in e for e in result.errors)


async def test_verify_rejects_mismatched_author_did() -> None:
    kp = generate_keypair()
    other = generate_keypair()
    artifact = build_question(keypair=kp, title="t", body="b", tags=[])
    tampered = {**artifact, "author_did": other.did}
    result = await verify_artifact(tampered)
    assert not result.ok


async def test_cid_deterministic_for_identical_bytes() -> None:
    kp = generate_keypair()
    common = {
        "keypair": kp,
        "title": "t",
        "body": "b",
        "tags": [],
        "created_at": "2026-04-24T00:00:00Z",
        "id": "01920000-0000-7000-8000-000000000000",
    }
    a = build_question(**common)
    b = build_question(**common)
    assert a["sig"]["sig"] == b["sig"]["sig"]
    assert await cid_of(a) == await cid_of(b)


async def test_build_answer_references_question_cid() -> None:
    q_kp = generate_keypair()
    a_kp = generate_keypair()
    q = build_question(keypair=q_kp, title="q", body="q body", tags=[])
    q_cid = await cid_of(q)
    answer = build_answer(keypair=a_kp, question_cid=q_cid, body="because X", refs=[])
    assert answer["kind"] == "answer"
    assert answer["question_cid"] == q_cid
    assert answer["author_did"] == a_kp.did
    v = await verify_artifact(answer)
    assert v.ok


async def test_build_answer_omits_refs_when_empty() -> None:
    kp = generate_keypair()
    a = build_answer(keypair=kp, question_cid="bafkdeadbeef", body="hi")
    assert "refs" not in a


async def test_build_rating_score_1_verifies() -> None:
    kp = generate_keypair()
    rating = build_rating(
        keypair=kp, target_cid="bafkfeedf00d", score=1, rationale="correct"
    )
    assert rating["score"] == 1
    assert rating["rationale"] == "correct"
    v = await verify_artifact(rating)
    assert v.ok


def test_build_rating_rejects_score_2() -> None:
    kp = generate_keypair()
    with pytest.raises(ValueError):
        build_rating(keypair=kp, target_cid="x", score=2)
