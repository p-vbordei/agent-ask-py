"""Mirror of `tests/store.test.ts`."""

from __future__ import annotations

import pytest

from agent_ask.artifact import build_answer, build_question, build_rating, cid_of
from agent_ask.identity import generate_keypair
from agent_ask.store import Store, open_store


@pytest.fixture()
def store() -> Store:
    s = open_store(":memory:")
    yield s
    s.close()


async def test_insert_and_get(store: Store) -> None:
    kp = generate_keypair()
    q = build_question(keypair=kp, title="t", body="b", tags=[])
    cid = await store.insert_artifact(q)
    assert cid == await cid_of(q)
    assert store.get_artifact(cid) == q


async def test_insert_is_idempotent(store: Store) -> None:
    kp = generate_keypair()
    q = build_question(
        keypair=kp, title="t", body="b", tags=[],
        created_at="2026-04-24T00:00:00Z",
        id="01920000-0000-7000-8000-000000000001",
    )
    c1 = await store.insert_artifact(q)
    c2 = await store.insert_artifact(q)
    assert c1 == c2
    assert len(store.list_questions()) == 1


async def test_list_filters_by_tag(store: Store) -> None:
    kp = generate_keypair()
    q1 = build_question(keypair=kp, title="a", body="b", tags=["x"])
    q2 = build_question(keypair=kp, title="b", body="b", tags=["y"])
    await store.insert_artifact(q1)
    await store.insert_artifact(q2)
    xs = store.list_questions(tag="x")
    assert [q["id"] for q in xs] == [q1["id"]]


async def test_list_filters_by_since_strict(store: Store) -> None:
    kp = generate_keypair()
    q1 = build_question(
        keypair=kp, title="a", body="b", tags=[], created_at="2026-04-01T00:00:00Z"
    )
    q2 = build_question(
        keypair=kp, title="b", body="b", tags=[], created_at="2026-05-01T00:00:00Z"
    )
    await store.insert_artifact(q1)
    await store.insert_artifact(q2)
    recent = store.list_questions(since="2026-04-15T00:00:00Z")
    assert [q["id"] for q in recent] == [q2["id"]]


async def test_stream_feed_newest_first(store: Store) -> None:
    kp = generate_keypair()
    q = build_question(
        keypair=kp, title="t", body="b", tags=[], created_at="2026-04-24T00:00:00Z"
    )
    q_cid = await store.insert_artifact(q)
    a = build_answer(
        keypair=kp, question_cid=q_cid, body="ans", created_at="2026-04-24T00:01:00Z"
    )
    a_cid = await store.insert_artifact(a)
    r = build_rating(
        keypair=kp, target_cid=a_cid, score=1, created_at="2026-04-24T00:02:00Z"
    )
    await store.insert_artifact(r)
    feed = list(store.stream_feed())
    assert len(feed) == 3
    assert feed[0]["kind"] == "rating"


def test_has_artifact_false_for_unknown(store: Store) -> None:
    assert store.has_artifact("bafkunknown") is False
