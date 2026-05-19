# Contributing

Thanks for considering a contribution to `agent-ask` (Python).

## Ground rules

- This repo is a **port**. The protocol's source of truth is [`@p-vbordei/agent-ask`](https://github.com/p-vbordei/agent-ask) (TS). Protocol-level changes go there first, then propagate here.
- Byte-determinism with the TS reference is non-negotiable. Any change that affects JCS bytes, the Ed25519 preimage, or the CIDv1 string MUST keep the C1–C3 conformance vectors passing.

## Dev setup

```bash
git clone https://github.com/p-vbordei/agent-ask-py
cd agent-ask-py
uv sync --extra dev
```

## Run the test suite

```bash
uv run pytest -q                  # all 60 tests
uv run pytest -k conformance -v   # just the SPEC vectors
```

## Lint + type-check

```bash
uv run ruff check src tests
uv run mypy src
```

## Style

- Stay close to the TS module layout (one Python module per TS file). The mapping is in [`docs/architecture.md`](docs/architecture.md).
- Public API lives in `agent_ask/__init__.py` — keep it in sync with the TS reference's `index.ts`.
- New behaviour requires a test. New protocol behaviour requires a vector that the TS reference also passes.

## Commit / PR flow

1. Branch from `main`.
2. Keep commits surgical and one logical change per PR.
3. Open a PR; CI must be green.

## Reporting issues

Issues at <https://github.com/p-vbordei/agent-ask-py/issues>. Protocol questions go on the [TS reference issue tracker](https://github.com/p-vbordei/agent-ask/issues).
