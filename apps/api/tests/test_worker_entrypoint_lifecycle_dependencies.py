from __future__ import annotations

from odei_api.execution_worker import _create_execution_run_store
from odei_api.parallel_execution_worker import _create_worker_stores


class FakeDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, object())


def test_execution_worker_entrypoint_injects_project_fence_and_shared_client():
    database = FakeDatabase()
    client, audit = object(), object()

    runs = _create_execution_run_store(database, client, audit)

    assert runs._client is client
    assert runs._projects is database["projects"]
    assert runs._audit is audit


def test_parallel_worker_entrypoint_injects_project_fence_and_shared_client():
    database = FakeDatabase()
    client, audit = object(), object()

    runs, jobs = _create_worker_stores(database, client, audit)

    assert runs._client is client
    assert runs._projects is database["projects"]
    assert runs._audit is audit
    assert jobs._client is client
    assert jobs._projects is database["projects"]
