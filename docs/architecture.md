# Architecture — agent-ask (Python port)

## Goal

Port [`@p-vbordei/agent-ask`](https://github.com/p-vbordei/agent-ask) (TS reference, npm v0.2.1) to idiomatic Python while staying byte-deterministic with the TS implementation. The same JCS bytes for the same artifact in any language; the same CIDv1 string; the same Ed25519 signature over the same canonical preimage.

## Module map

Each Python module mirrors one TS file. The public API in `agent_ask/__init__.py` re-exports the names below.

| `agent_ask/` (Python) | `src/` (TS reference) | Responsibility |
|---|---|---|
| `canonical.py` | `canonical.ts` | RFC 8785 JCS; `artifact_bytes_for_sig`; CIDv1 raw+sha256 with `b` multibase prefix. |
| `identity.py` | `identity.ts` | Ed25519 keypair, `did:key:` derivation, sign / verify, base64 pubkey codec. |
| `artifact.py` | `artifact.ts` | `build_question`, `build_answer`, `build_rating`; strict schema validation; `verify_artifact`; `cid_of`. |
| `store.py` | `store.ts` | SQLite-backed CRUD (`:memory:` or file path). Idempotent inserts keyed on CID. |
| `federation.py` | `federation.ts` | `pull_from_peer(url, since)`: stream NDJSON `/feed`, verify each line, dedup against local store. |
| `server.py` | `server.ts` | FastAPI app exposing `POST /questions|/answers|/ratings`, `GET /artifact/{cid}|/questions|/feed`. |

## Dependency choices

| Concern | Pick | Why |
|---|---|---|
| HTTP server | FastAPI + uvicorn | Idiomatic Python async; trivial in-process testing via Starlette `TestClient`; minimal boilerplate. |
| SQLite | stdlib `sqlite3` | No extra wheel; one-line `:memory:` for tests. |
| Ed25519 | `cryptography` | Single dep covers sign / verify / DID-key. |
| JCS | [`jcs`](https://pypi.org/project/jcs/) | Direct RFC 8785 encoder; matches TS canonicalize byte-for-byte. |
| HTTP client | `httpx` | Async streaming `iter_lines` for NDJSON. |
| base64url DID payload | `base58` | `did:key:` uses multibase, base58btc with `z` prefix. |

## Byte-determinism invariants

These two strings MUST match what the TS reference would produce for the same logical artifact:

1. **JCS preimage.** `artifact_bytes_for_sig(a)` = `jcs(a \ "sig")` — strict key ordering, UTF-8, no whitespace, canonical numbers. Cross-checked by `tests/test_canonical.py` against fixed vectors.
2. **CIDv1 string.** `b` + base32-lower-no-pad of (`0x01 0x55 0x12 0x20` + sha256(preimage)). Cross-checked by `tests/test_conformance.py` against `vectors/C1-roundtrip`.

If either drifts, federation breaks — peers will refuse / fail to dedup.

## Testing strategy

Three layers:

- **Unit.** One file per module (`test_canonical.py`, `test_identity.py`, `test_artifact.py`, `test_store.py`, `test_federation.py`).
- **In-process HTTP.** `test_server.py` uses `fastapi.testclient.TestClient` to drive `create_app(AppConfig(...))` without binding a real port — fast and deterministic; supports an injectable `now_fn` for the ±24h ingest window edges.
- **Conformance.** `test_conformance.py` loads `vectors/C{1,2,3}-*/` and replays the same byte-identical fixtures used by the TS test suite. 60 tests total.

```bash
uv sync --extra dev
uv run pytest -q
```
