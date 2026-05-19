"""FastAPI server (mirror of `src/server.ts`).

Exposes:
  POST /questions, POST /answers, POST /ratings
  GET  /artifact/{cid}, GET /questions?tag=&since=
  GET  /feed?since=<iso>

The `create_app(...)` factory returns a `FastAPI` instance bound to a `Store`
and an optional `now_fn` (for deterministic tests).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .artifact import Artifact, verify_artifact
from .store import Store, open_store

MAX_BODY = 64 * 1024


@dataclass
class AppConfig:
    store: Store
    now_fn: Callable[[], datetime] | None = None


def _parse_iso(s: str) -> int:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return int(datetime.fromisoformat(s).astimezone(timezone.utc).timestamp() * 1000)


def create_app(config: AppConfig) -> FastAPI:
    app = FastAPI()
    now = config.now_fn or (lambda: datetime.now(tz=timezone.utc))

    async def ingest(body: Any, expected_kind: str) -> tuple[int, dict[str, Any]]:
        v = await verify_artifact(body)
        if not v.ok:
            return 400, {"error": f"verify: {'; '.join(v.errors)}"}
        artifact: Artifact = body
        if artifact["kind"] != expected_kind:
            return 400, {"error": f"kind mismatch: expected {expected_kind}"}
        now_ms = int(now().astimezone(timezone.utc).timestamp() * 1000)
        try:
            created_ms = _parse_iso(artifact["created_at"])
        except Exception:
            return 400, {"error": "invalid created_at"}
        if abs(now_ms - created_ms) > 24 * 60 * 60 * 1000:
            return 400, {"error": "created_at outside ±24h window"}
        if artifact["kind"] == "answer" and not config.store.has_artifact(artifact["question_cid"]):
            return 400, {"error": "question_cid not known locally"}
        if artifact["kind"] == "rating" and not config.store.has_artifact(artifact["target_cid"]):
            return 400, {"error": "target_cid not known locally"}
        cid = await config.store.insert_artifact(artifact)
        return 201, {"cid": cid}

    async def handle_post(request: Request, kind: str) -> Response:
        cl_header = request.headers.get("content-length")
        if cl_header is not None:
            try:
                if int(cl_header) > MAX_BODY:
                    return JSONResponse({"error": "body too large"}, status_code=413)
            except ValueError:
                pass
        raw = await request.body()
        if len(raw) > MAX_BODY:
            return JSONResponse({"error": "body too large"}, status_code=413)
        if not raw:
            return JSONResponse({"error": "invalid json"}, status_code=400)
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return JSONResponse({"error": "invalid json"}, status_code=400)
        status, payload = await ingest(body, kind)
        return JSONResponse(payload, status_code=status)

    @app.post("/questions")
    async def post_question(request: Request) -> Response:
        return await handle_post(request, "question")

    @app.post("/answers")
    async def post_answer(request: Request) -> Response:
        return await handle_post(request, "answer")

    @app.post("/ratings")
    async def post_rating(request: Request) -> Response:
        return await handle_post(request, "rating")

    @app.get("/artifact/{cid}")
    async def get_artifact(cid: str) -> Response:
        artifact = config.store.get_artifact(cid)
        if artifact is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(artifact)

    @app.get("/questions")
    async def get_questions(request: Request) -> Response:
        tag = request.query_params.get("tag")
        since = request.query_params.get("since")
        return JSONResponse(config.store.list_questions(tag=tag, since=since))

    @app.get("/feed")
    async def get_feed(request: Request) -> Response:
        since = request.query_params.get("since")

        def gen() -> Any:
            for artifact in config.store.stream_feed(since=since):
                yield json.dumps(artifact, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"

        return StreamingResponse(gen(), media_type="application/x-ndjson; charset=utf-8")

    return app


def main() -> None:
    import os
    import uvicorn

    db_path = os.environ.get("AGENT_ASK_DB", "./agent-ask.db")
    port = int(os.environ.get("AGENT_ASK_PORT", "8787"))
    store = open_store(db_path)
    app = create_app(AppConfig(store=store))
    uvicorn.run(app, host="0.0.0.0", port=port)
