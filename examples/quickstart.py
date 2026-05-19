"""agent-ask Python quickstart.

Spins an in-process FastAPI app via TestClient, posts a signed Question,
retrieves it via the HTTP API, then verifies CID + signature match.

Run:
    uv run python examples/quickstart.py
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from agent_ask import (
    AppConfig,
    build_question,
    cid_of,
    create_app,
    generate_keypair,
    open_store,
    verify_artifact,
)


async def main() -> None:
    # 1. In-memory store, fresh DID-bound Ed25519 keypair, in-process HTTP app.
    store = open_store(":memory:")
    kp = generate_keypair()
    client = TestClient(create_app(AppConfig(store=store)))

    # 2. Build a signed Question artifact and predict its CID.
    q = build_question(
        keypair=kp,
        title="Why CIDv1 raw+sha256?",
        body="So any JCS-compatible runtime computes the same id.",
        tags=["meta", "cid"],
    )
    expected_cid = await cid_of(q)
    print(f"author = {kp.did[:24]}...")
    print(f"cid    = {expected_cid}")

    # 3. POST it to the in-process server.
    res = client.post("/questions", json=q)
    print(f"POST /questions -> {res.status_code} {res.json()}")
    assert res.status_code == 201
    assert res.json() == {"cid": expected_cid}

    # 4. Fetch back over HTTP and verify CID + signature roundtrip.
    fetched = client.get(f"/artifact/{expected_cid}").json()
    assert await cid_of(fetched) == expected_cid, "CID mismatch — JCS bytes drifted"
    verified = await verify_artifact(fetched)
    assert verified.ok, verified.errors
    print(f"GET  /artifact/{expected_cid[:14]}... -> verified={verified.ok}")

    store.close()
    print("ok")


if __name__ == "__main__":
    asyncio.run(main())
