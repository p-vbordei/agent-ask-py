"""Mirror of `tests/e2e-lib.test.ts`."""

from __future__ import annotations

from agent_ask.artifact import build_question, cid_of, verify_artifact
from agent_ask.identity import generate_keypair


async def test_build_verify_recompute_cid_byte_identical_rebuild() -> None:
    kp = generate_keypair()
    common = dict(
        keypair=kp,
        title="does this work?",
        body="I am an agent asking another agent.",
        tags=["smoke", "meta"],
        created_at="2026-04-24T12:00:00Z",
        id="01920000-0000-7000-8000-000000000abc",
    )
    a = build_question(**common)
    b = build_question(**common)
    v = await verify_artifact(a)
    assert v.ok
    assert a["sig"]["sig"] == b["sig"]["sig"]
    assert await cid_of(a) == await cid_of(b)
