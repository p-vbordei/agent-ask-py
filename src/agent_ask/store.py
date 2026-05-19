"""SQLite-backed artifact store (mirror of `src/store.ts`).

`path` may be `:memory:` for an ephemeral store.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterator

from .artifact import Artifact, cid_of_sync

_SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
  cid TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  created_at TEXT NOT NULL,
  body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifacts_kind_created ON artifacts(kind, created_at);
CREATE INDEX IF NOT EXISTS idx_artifacts_created ON artifacts(created_at);

CREATE TABLE IF NOT EXISTS question_tags (
  cid TEXT NOT NULL,
  tag TEXT NOT NULL,
  PRIMARY KEY (cid, tag),
  FOREIGN KEY (cid) REFERENCES artifacts(cid) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_question_tags_tag ON question_tags(tag);
"""


class Store:
    def __init__(self, path: str) -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode = WAL;")
        self._db.execute("PRAGMA foreign_keys = ON;")
        self._db.executescript(_SCHEMA)

    async def insert_artifact(self, artifact: Artifact) -> str:
        cid = cid_of_sync(artifact)
        body = json.dumps(artifact, separators=(",", ":"), sort_keys=False, ensure_ascii=False)
        self._db.execute(
            "INSERT OR IGNORE INTO artifacts(cid, kind, created_at, body) VALUES (?, ?, ?, ?)",
            (cid, artifact["kind"], artifact["created_at"], body),
        )
        if artifact["kind"] == "question":
            for tag in artifact.get("tags", []):
                self._db.execute(
                    "INSERT OR IGNORE INTO question_tags(cid, tag) VALUES (?, ?)",
                    (cid, tag),
                )
        self._db.commit()
        return cid

    def get_artifact(self, cid: str) -> Artifact | None:
        row = self._db.execute("SELECT body FROM artifacts WHERE cid = ?", (cid,)).fetchone()
        return json.loads(row[0]) if row else None

    def has_artifact(self, cid: str) -> bool:
        return self._db.execute("SELECT 1 FROM artifacts WHERE cid = ?", (cid,)).fetchone() is not None

    def list_questions(
        self,
        *,
        tag: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[Artifact]:
        clauses: list[str] = ["a.kind = 'question'"]
        params: list[Any] = []
        if tag:
            clauses.append("qt.tag = ?")
            params.append(tag)
        if since:
            clauses.append("a.created_at > ?")
            params.append(since)
        join = "JOIN question_tags qt ON qt.cid = a.cid" if tag else ""
        sql = (
            f"SELECT DISTINCT a.body FROM artifacts a {join} "
            f"WHERE {' AND '.join(clauses)} "
            f"ORDER BY a.created_at DESC LIMIT ?"
        )
        params.append(limit)
        rows = self._db.execute(sql, params).fetchall()
        return [json.loads(r[0]) for r in rows]

    def stream_feed(
        self,
        *,
        since: str | None = None,
        limit: int = 1000,
    ) -> Iterator[Artifact]:
        clauses: list[str] = []
        params: list[Any] = []
        if since:
            clauses.append("created_at > ?")
            params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT body FROM artifacts {where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        for row in self._db.execute(sql, params).fetchall():
            yield json.loads(row[0])

    def close(self) -> None:
        self._db.close()


def open_store(path: str) -> Store:
    return Store(path)
