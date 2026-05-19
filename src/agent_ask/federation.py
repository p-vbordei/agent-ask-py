"""Pull-import federation (mirror of `src/federation.ts`)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from urllib.parse import quote

import httpx

from .artifact import Artifact, cid_of_sync, verify_artifact
from .store import Store

FetchFn = Callable[[str], Awaitable["FetchResponse"]]


@dataclass
class FetchResponse:
    status: int
    text: str

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


@dataclass
class PullResult:
    count: int = 0
    rejected: int = 0
    last_seen: str | None = None
    reasons: list[str] = field(default_factory=list)


async def _default_fetch(url: str) -> FetchResponse:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url)
        return FetchResponse(status=r.status_code, text=r.text)


def _parse_iso_z(s: str) -> int:
    # Accept the canonical "...Z" form and a few common variants for nowFn-supplied values.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return int(datetime.fromisoformat(s).astimezone(timezone.utc).timestamp() * 1000)


async def pull_from_peer(
    *,
    peer_url: str,
    store: Store,
    since: str | None = None,
    fetch_fn: FetchFn | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> PullResult:
    fetch = fetch_fn or _default_fetch
    now_dt = (now_fn or (lambda: datetime.now(tz=timezone.utc)))()
    now_ms = int(now_dt.astimezone(timezone.utc).timestamp() * 1000)

    url = f"{peer_url}/feed?since={quote(since, safe='')}" if since else f"{peer_url}/feed"
    res = await fetch(url)
    if not res.ok:
        raise RuntimeError(f"peer {peer_url} returned {res.status}")

    result = PullResult()
    last_seen: str | None = None

    def advance(created_at: str) -> str | None:
        nonlocal last_seen
        if last_seen is None or created_at > last_seen:
            last_seen = created_at
        return last_seen

    # TS reverses the feed so older-first is processed first; this matters for
    # the answer→question dependency check when the feed is newest-first.
    for line in reversed(res.text.split("\n")):
        trimmed = line.strip()
        if not trimmed:
            continue
        try:
            raw: Any = json.loads(trimmed)
        except json.JSONDecodeError:
            result.reasons.append("invalid json line")
            continue
        v = await verify_artifact(raw)
        if not v.ok:
            result.reasons.append(f"verify: {v.errors[0] if v.errors else 'unknown'}")
            continue
        a: Artifact = raw
        try:
            created_ms = _parse_iso_z(a["created_at"])
        except Exception:  # noqa: BLE001
            result.reasons.append("invalid created_at")
            continue
        if abs(now_ms - created_ms) > 24 * 60 * 60 * 1000:
            result.reasons.append("created_at outside ±24h window")
            continue
        if a["kind"] == "answer" and not store.has_artifact(a["question_cid"]):
            result.reasons.append("answer references unknown question_cid")
            continue
        if a["kind"] == "rating" and not store.has_artifact(a["target_cid"]):
            result.reasons.append("rating references unknown target_cid")
            continue
        # Verified — advance cursor even on duplicate so it doesn't stall.
        advance(a["created_at"])
        cid = cid_of_sync(a)
        if store.has_artifact(cid):
            continue
        await store.insert_artifact(a)
        result.count += 1

    result.last_seen = last_seen
    result.rejected = len(result.reasons)
    return result
