from __future__ import annotations

from datetime import datetime, timedelta, timezone

from odei_api.services.repository_analysis import analyze_repository
from odei_api.services.repository_index_store import MongoRepositoryIndexStore


def test_python_symbols_references_and_import_edges_are_extracted():
    result = analyze_repository([
        {
            "path": "src/service.py",
            "content": "import os\n\nclass Worker:\n    def run(self):\n        return build()\n",
        },
        {
            "path": "src/build.py",
            "content": "def build():\n    return 'ready'\n",
        },
    ])
    symbols = {(item["name"], item["kind"], item["path"]) for item in result["symbols"]}
    assert ("Worker", "class", "src/service.py") in symbols
    assert ("run", "function", "src/service.py") in symbols
    assert ("build", "function", "src/build.py") in symbols
    assert any(
        item["name"] == "build" and item["path"] == "src/service.py"
        for item in result["references"]
    )
    assert {"path": "src/service.py", "module": "os"} in result["imports"]


def test_javascript_symbols_imports_and_cross_file_references_are_extracted():
    result = analyze_repository([
        {
            "path": "src/worker.js",
            "content": "export function startWorker() { return true; }\n",
        },
        {
            "path": "src/main.js",
            "content": "import { startWorker } from './worker.js';\nstartWorker();\n",
        },
    ])
    assert any(
        item["name"] == "startWorker" and item["kind"] == "function"
        and item["path"] == "src/worker.js"
        for item in result["symbols"]
    )
    assert {"path": "src/main.js", "module": "./worker.js"} in result["imports"]
    assert any(
        item["name"] == "startWorker" and item["path"] == "src/main.js"
        and item["line"] == 2
        for item in result["references"]
    )


def test_retrieval_chunks_are_bounded_and_report_truncation():
    result = analyze_repository([
        {"path": "a.py", "content": "\n".join(f"line_{i}" for i in range(1, 40))},
        {"path": "b.py", "content": "\n".join(f"other_{i}" for i in range(1, 40))},
    ], max_chunks=1)
    assert len(result["chunks"]) == 1
    assert result["chunk_limit_reached"] is True
    assert result["chunks"][0]["line_start"] == 1


class Cursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def sort(self, *_args):
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    async def to_list(self, length):
        return self.rows[:length]


class Collection:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.last_query = None

    async def find_one(self, query):
        self.last_query = query
        for row in self.rows:
            if all(
                row.get(key) > value["$gt"] if isinstance(value, dict) and "$gt" in value
                else row.get(key) == value
                for key, value in query.items()
            ):
                return row
        return None

    def find(self, query, *_args):
        self.last_query = query
        return Cursor([
            row for row in self.rows
            if all(row.get(key) == value for key, value in query.items())
        ])


class Database:
    def __init__(self, collections):
        self.collections = collections

    def __getitem__(self, key):
        return self.collections.setdefault(key, Collection())


async def test_semantic_search_is_revision_and_tenant_scoped():
    expires = datetime.now(timezone.utc) + timedelta(days=1)
    database = Database({
        "repository_index_state": Collection([{
            "organization_id": "org-a", "project_id": "project-a",
            "revision": 4, "revision_id": "revision-a", "expires_at": expires,
        }]),
        "repository_index_chunks": Collection([
            {
                "organization_id": "org-a", "project_id": "project-a",
                "revision_id": "revision-a", "path": "src/a.py",
                "chunk_index": 0, "line_start": 3, "text": "closest",
                "embedding": [1.0, 0.0], "sha256": "a" * 64,
                "revision": 4, "snapshot_id": "snapshot-a",
            },
            {
                "organization_id": "org-a", "project_id": "project-a",
                "revision_id": "revision-a", "path": "src/b.py",
                "chunk_index": 0, "line_start": 1, "text": "orthogonal",
                "embedding": [0.0, 1.0], "sha256": "b" * 64,
                "revision": 4, "snapshot_id": "snapshot-a",
            },
            {
                "organization_id": "org-b", "project_id": "project-a",
                "revision_id": "revision-a", "path": "private.py",
                "chunk_index": 0, "line_start": 1, "text": "other tenant",
                "embedding": [1.0, 0.0], "sha256": "c" * 64,
                "revision": 4, "snapshot_id": "snapshot-b",
            },
        ]),
    })
    store = MongoRepositoryIndexStore(database)
    results = await store.search_semantic(
        organization_id="org-a", project_id="project-a",
        query_embedding=[1.0, 0.0], limit=2,
    )
    assert [item["path"] for item in results] == ["src/a.py", "src/b.py"]
    assert results[0]["score"] == 1.0
    assert database["repository_index_chunks"].last_query == {
        "organization_id": "org-a", "project_id": "project-a",
        "revision_id": "revision-a",
    }
