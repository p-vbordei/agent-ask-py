"""Mirror of `tests/federation.test.ts`."""

from __future__ import annotations

import json
from typing import Awaitable, Callable

import pytest
from fastapi.testclient import TestClient

from agent_ask.artifact import build_answer, build_question, cid_of
from agent_ask.federation import FetchResponse, pull_from_peer
from agent_ask.identity import generate_keypair
from agent_ask.server import AppConfig, create_app
from agent_ask.store import Store, open_store


@pytest.fixture()
def peer_store() -> Store:
    s = open_store(":memory:")
    yield s
    s.close()


@pytest.fixture()
def local_store() -> Store:
    s = open_store(":memory:")
    yield s
    s.close()


def _peer_fetch(peer_app_client: TestClient) -> Callable[[str], Awaitable[FetchResponse]]:
    async def fetch(url: str) -> FetchResponse:
        # `url` is like "http://peer/feed?since=..."; strip the host prefix.
        if url.startswith("http://peer"):
            path = url[len("http://peer") :]
        else:
            path = url
        r = peer_app_client.get(path)
        return FetchResponse(status=r.status_code, text=r.text)

    return fetch


async def test_pull_ingests_all(peer_store: Store, local_store: Store) -> None:
    peer_app = create_app(AppConfig(store=peer_store))
    peer = TestClient(peer_app)
    kp = generate_keypair()
    q = build_question(keypair=kp, title="t", body="b", tags=[])
    peer.post("/questions", json=q)
    q_cid = await cid_of(q)
    a = build_answer(keypair=kp, question_cid=q_cid, body="ans")
    a_cid = await cid_of(a)
    peer.post("/answers", json=a)

    res = await pull_from_peer(
        peer_url="http://peer",
        store=local_store,
        fetch_fn=_peer_fetch(peer),
    )
    assert res.count == 2
    assert res.last_seen == a["created_at"]
    assert local_store.get_artifact(q_cid) == q
    assert local_store.get_artifact(a_cid) == a


async def test_pull_idempotent(peer_store: Store, local_store: Store) -> None:
    peer_app = create_app(AppConfig(store=peer_store))
    peer = TestClient(peer_app)
    kp = generate_keypair()
    q = build_question(keypair=kp, title="t", body="b", tags=[])
    peer.post("/questions", json=q)
    fetch = _peer_fetch(peer)
    first = await pull_from_peer(peer_url="http://peer", store=local_store, fetch_fn=fetch)
    second = await pull_from_peer(peer_url="http://peer", store=local_store, fetch_fn=fetch)
    assert first.count == 1
    assert second.count == 0


async def test_pull_discards_invalid(local_store: Store) -> None:
    kp = generate_keypair()
    q = build_question(keypair=kp, title="t", body="b", tags=[])
    tampered = {**q, "body": "MUTATED"}
    fake_feed = json.dumps(tampered) + "\n"

    async def fetch(_url: str) -> FetchResponse:
        return FetchResponse(status=200, text=fake_feed)

    res = await pull_from_peer(peer_url="http://peer", store=local_store, fetch_fn=fetch)
    assert res.count == 0
    assert res.rejected == 1
    assert len(res.reasons) == 1
    assert "verify" in res.reasons[0]
    assert not local_store.has_artifact(await cid_of(q))


async def test_pull_advances_lastseen_on_duplicate(
    peer_store: Store, local_store: Store
) -> None:
    peer_app = create_app(AppConfig(store=peer_store))
    peer = TestClient(peer_app)
    kp = generate_keypair()
    q = build_question(keypair=kp, title="t", body="b", tags=[])
    peer.post("/questions", json=q)
    fetch = _peer_fetch(peer)
    first = await pull_from_peer(peer_url="http://peer", store=local_store, fetch_fn=fetch)
    second = await pull_from_peer(peer_url="http://peer", store=local_store, fetch_fn=fetch)
    assert first.last_seen == q["created_at"]
    assert second.count == 0
    assert second.last_seen == q["created_at"]


async def test_pull_reasons_enumerate(local_store: Store) -> None:
    kp = generate_keypair()
    q = build_question(keypair=kp, title="t", body="b", tags=[])
    tampered = {**q, "body": "X"}
    feed = "{not json}\n" + json.dumps(tampered)

    async def fetch(_url: str) -> FetchResponse:
        return FetchResponse(status=200, text=feed)

    res = await pull_from_peer(peer_url="http://peer", store=local_store, fetch_fn=fetch)
    assert res.rejected == 2
    assert "invalid json line" in res.reasons
    assert any(r.startswith("verify:") for r in res.reasons)
