# Changelog

All notable changes to this project are documented in this file. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning: [SemVer](https://semver.org/).

## [Unreleased]

## [0.1.0] — 2026-05-19

### Added

- `identity` — Ed25519 keypair, `did:key:` derivation, sign + verify (`generate_keypair`, `sign`, `verify`, `did_from_pubkey`, `pubkey_from_did`).
- `artifact` — Question / Answer / Rating builders, strict schema validation, `verify_artifact`, `cid_of` (CIDv1 raw+sha256).
- `canonical` — RFC 8785 JCS encoder, `artifact_bytes_for_sig`, `compute_cid`.
- `store` — SQLite-backed CRUD (`open_store(":memory:")` or file path), idempotent inserts keyed on CID.
- `federation.pull_from_peer(peer_url, since)` — stream NDJSON `/feed`, verify each line, dedup.
- `server.create_app(AppConfig(...))` — FastAPI app exposing six protocol endpoints (`POST /questions|/answers|/ratings`, `GET /artifact/{cid}|/questions|/feed`) with ±24h ingest window and 64 KiB body cap.
- `agent-ask` CLI entry point — uvicorn server bound to env vars `AGENT_ASK_DB`, `AGENT_ASK_PORT`.
- Byte-deterministic conformance with the TS reference: all C1 (roundtrip), C2 (tamper detection), C3 (federation pull) vectors pass.
- In-process HTTP test harness using `fastapi.testclient.TestClient`.
- 60 tests pass.

[Unreleased]: https://github.com/p-vbordei/agent-ask-py/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/p-vbordei/agent-ask-py/releases/tag/v0.1.0
