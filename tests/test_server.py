"""Mirror of `tests/server.test.ts` + `tests/ingest-edges.test.ts`."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from agent_ask.artifact import build_answer, build_question, build_rating, cid_of
from agent_ask.identity import generate_keypair
from agent_ask.server import AppConfig, create_app
from agent_ask.store import Store, open_store


@pytest.fixture()
def store() -> Store:
    s = open_store(":memory:")
    yield s
    s.close()


@pytest.fixture()
def client(store: Store) -> TestClient:
    app = create_app(AppConfig(store=store))
    return TestClient(app)


async def test_post_question_201(store: Store, client: TestClient) -> None:
    kp = generate_keypair()
    q = build_question(keypair=kp, title="t", body="b", tags=[])
    q_cid = await cid_of(q)
    res = client.post("/questions", json=q)
    assert res.status_code == 201
    assert res.json() == {"cid": q_cid}
    assert store.has_artifact(q_cid)


def test_post_question_tampered_400(client: TestClient) -> None:
    kp = generate_keypair()
    q = build_question(keypair=kp, title="t", body="b", tags=[])
    tampered = {**q, "body": "mutated"}
    res = client.post("/questions", json=tampered)
    assert res.status_code == 400


def test_post_answer_requires_known_question(client: TestClient) -> None:
    kp = generate_keypair()
    a = build_answer(keypair=kp, question_cid="bafkmissing", body="orphan")
    res = client.post("/answers", json=a)
    assert res.status_code == 400


def test_post_rating_requires_known_target(client: TestClient) -> None:
    kp = generate_keypair()
    r = build_rating(keypair=kp, target_cid="bafkmissing", score=1)
    res = client.post("/ratings", json=r)
    assert res.status_code == 400


def test_post_questions_with_kind_answer_400(client: TestClient) -> None:
    kp = generate_keypair()
    q = build_question(keypair=kp, title="t", body="b", tags=[])
    mismatched = {**q, "kind": "answer"}
    res = client.post("/questions", json=mismatched)
    assert res.status_code == 400


async def test_get_artifact_returns_stored(client: TestClient) -> None:
    kp = generate_keypair()
    q = build_question(keypair=kp, title="t", body="b", tags=["x"])
    q_cid = await cid_of(q)
    client.post("/questions", json=q)
    res = client.get(f"/artifact/{q_cid}")
    assert res.status_code == 200
    body = res.json()
    assert body == q
    assert "cid" not in body


def test_get_artifact_404(client: TestClient) -> None:
    res = client.get("/artifact/bafkunknown")
    assert res.status_code == 404


def test_get_questions_filters_by_tag(client: TestClient) -> None:
    kp = generate_keypair()
    q1 = build_question(keypair=kp, title="a", body="b", tags=["x"])
    q2 = build_question(keypair=kp, title="b", body="b", tags=["y"])
    client.post("/questions", json=q1)
    client.post("/questions", json=q2)
    res = client.get("/questions?tag=x")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["id"] == q1["id"]


def test_get_feed_ndjson(client: TestClient) -> None:
    kp = generate_keypair()
    q = build_question(keypair=kp, title="t", body="b", tags=[])
    client.post("/questions", json=q)
    res = client.get("/feed")
    assert res.status_code == 200
    assert "application/x-ndjson" in res.headers["content-type"]
    lines = [ln for ln in res.text.strip().split("\n") if ln]
    assert len(lines) == 1
    assert json.loads(lines[0]) == q


async def test_get_feed_since_cutoff(store: Store) -> None:
    app = create_app(AppConfig(store=store))
    c = TestClient(app)
    kp = generate_keypair()
    q1 = build_question(keypair=kp, title="a", body="b", tags=[], created_at="2026-04-01T00:00:00Z")
    q2 = build_question(keypair=kp, title="b", body="b", tags=[], created_at="2026-05-01T00:00:00Z")
    await store.insert_artifact(q1)
    await store.insert_artifact(q2)
    res = c.get("/feed?since=2026-04-15T00:00:00Z")
    lines = [ln for ln in res.text.strip().split("\n") if ln]
    assert len(lines) == 1
    assert json.loads(lines[0])["id"] == q2["id"]


def test_post_413_with_content_length(store: Store) -> None:
    app = create_app(AppConfig(store=store))
    c = TestClient(app)
    huge = "x" * (64 * 1024 + 100)
    body = json.dumps({"junk": huge}).encode()
    res = c.post(
        "/questions",
        content=body,
        headers={"content-type": "application/json", "content-length": str(len(body))},
    )
    assert res.status_code == 413


def test_post_413_streamed(store: Store) -> None:
    app = create_app(AppConfig(store=store))
    c = TestClient(app)
    huge = "x" * (64 * 1024 + 100)
    body = json.dumps({"junk": huge}).encode()
    # TestClient always sends content-length, but the post handler reads stream too —
    # this still hits the 413 branch.
    res = c.post("/questions", content=body, headers={"content-type": "application/json"})
    assert res.status_code == 413


def test_post_invalid_json_400(client: TestClient) -> None:
    res = client.post(
        "/questions", content=b"{not json", headers={"content-type": "application/json"}
    )
    assert res.status_code == 400
    assert "invalid json" in res.json()["error"]


def test_post_empty_body_400(client: TestClient) -> None:
    res = client.post(
        "/questions", content=b"", headers={"content-type": "application/json"}
    )
    assert res.status_code == 400


# ---- ingest edges (SPEC §3.1) ----


def _fixed_now() -> datetime:
    return datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)


def test_rejects_48h_past(store: Store) -> None:
    app = create_app(AppConfig(store=store, now_fn=_fixed_now))
    c = TestClient(app)
    kp = generate_keypair()
    q = build_question(
        keypair=kp, title="t", body="b", tags=[], created_at="2026-04-22T11:59:00Z"
    )
    res = c.post("/questions", json=q)
    assert res.status_code == 400
    assert "24h" in res.json()["error"]


def test_rejects_48h_future(store: Store) -> None:
    app = create_app(AppConfig(store=store, now_fn=_fixed_now))
    c = TestClient(app)
    kp = generate_keypair()
    q = build_question(
        keypair=kp, title="t", body="b", tags=[], created_at="2026-04-26T12:01:00Z"
    )
    assert c.post("/questions", json=q).status_code == 400


def test_accepts_23h_boundary(store: Store) -> None:
    app = create_app(AppConfig(store=store, now_fn=_fixed_now))
    c = TestClient(app)
    kp = generate_keypair()
    q = build_question(
        keypair=kp, title="t", body="b", tags=[], created_at="2026-04-25T11:00:00Z"
    )
    assert c.post("/questions", json=q).status_code == 201


def test_rejects_pubkey_author_mismatch(client: TestClient) -> None:
    kp = generate_keypair()
    other = generate_keypair()
    q = build_question(keypair=kp, title="t", body="b", tags=[])
    swapped = {**q, "author_did": other.did}
    assert client.post("/questions", json=swapped).status_code == 400


def test_rejects_fractional_seconds(client: TestClient) -> None:
    kp = generate_keypair()
    q = build_question(
        keypair=kp, title="t", body="b", tags=[], created_at="2026-04-25T12:00:00.000Z"
    )
    res = client.post("/questions", json=q)
    assert res.status_code == 400
    assert "created_at" in res.json()["error"]


def test_rejects_plus_offset(client: TestClient) -> None:
    kp = generate_keypair()
    q = build_question(
        keypair=kp, title="t", body="b", tags=[], created_at="2026-04-25T12:00:00+00:00"
    )
    assert client.post("/questions", json=q).status_code == 400


def test_rejects_rating_unknown_target(client: TestClient) -> None:
    kp = generate_keypair()
    r = build_rating(keypair=kp, target_cid="bafkdeadbeef", score=1)
    assert client.post("/ratings", json=r).status_code == 400


def test_duplicate_post_idempotent(client: TestClient) -> None:
    kp = generate_keypair()
    q = build_question(keypair=kp, title="t", body="b", tags=[])
    r1 = client.post("/questions", json=q)
    r2 = client.post("/questions", json=q)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["cid"] == r2.json()["cid"]
