"""Conformance vectors from `vectors/` (mirrors `conformance/run.ts`)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent_ask.artifact import cid_of, verify_artifact
from agent_ask.federation import FetchResponse, pull_from_peer
from agent_ask.store import open_store

VECTORS = Path(__file__).resolve().parent.parent / "vectors"

C1 = sorted((VECTORS / "C1-roundtrip").glob("*.json"))
C2 = sorted((VECTORS / "C2-tamper").glob("*.json"))


@pytest.mark.parametrize("path", C1, ids=[p.name for p in C1])
async def test_c1_roundtrip(path: Path) -> None:
    raw = json.loads(path.read_text())
    v = await verify_artifact(raw)
    assert v.ok, f"verify failed: {v.errors}"


@pytest.mark.parametrize("path", C2, ids=[p.name for p in C2])
async def test_c2_tamper(path: Path) -> None:
    raw = json.loads(path.read_text())
    v = await verify_artifact(raw)
    assert not v.ok, "expected verification to fail, but it passed"


async def test_c3_pull_import_byte_identical() -> None:
    feed_text = (VECTORS / "C3-federation" / "feed.ndjson").read_text()
    expected = [json.loads(l) for l in feed_text.split("\n") if l]

    async def fetch(_url: str) -> FetchResponse:
        return FetchResponse(status=200, text=feed_text)

    newest = max(expected, key=lambda a: a["created_at"])
    iso = newest["created_at"]
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    fixed = datetime.fromisoformat(iso).astimezone(timezone.utc)

    store = open_store(":memory:")
    try:
        res = await pull_from_peer(
            peer_url="http://peer",
            store=store,
            fetch_fn=fetch,
            now_fn=lambda: fixed,
        )
        assert res.count == len(expected), f"rejected: {res.reasons}"
        for art in expected:
            cid = await cid_of(art)
            assert store.has_artifact(cid)
            got = store.get_artifact(cid)
            assert json.dumps(got, sort_keys=True) == json.dumps(art, sort_keys=True)
    finally:
        store.close()
