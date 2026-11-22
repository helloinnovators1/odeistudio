from __future__ import annotations

from copy import deepcopy

import pytest

from odei_api.services.mac_environment_migrations import (
    MacRevisionMigrationConflict,
    backfill_mac_environment_revisions,
    initialize_mac_revision_collection,
)


class Cursor:
    def __init__(self, records):
        self.records = records

    def __aiter__(self):
        self._iterator = iter(self.records)
        return self

    async def __anext__(self):
        try:
            return deepcopy(next(self._iterator))
        except StopIteration:
            raise StopAsyncIteration


class Environments:
    def __init__(self, records):
        self.records = records

    def find(self, _query, session=None):
        assert session == "transaction"
        return Cursor(self.records)


class Revisions:
    def __init__(self, records=None):
        self.records = {item["_id"]: deepcopy(item) for item in (records or [])}
        self.indexes = []

    async def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))

    async def find_one(self, query, session=None):
        assert session == "transaction"
        return deepcopy(self.records.get(query["_id"]))

    async def insert_one(self, document, session=None):
        assert session == "transaction"
        if document["_id"] in self.records:
            raise AssertionError("duplicate insert")
        self.records[document["_id"]] = deepcopy(document)


@pytest.mark.asyncio
async def test_revision_backfill_is_idempotent_and_preserves_history():
    legacy = [{
        "_id": "staging",
        "environment": "staging",
        "latest_version": 2,
        "versions": [
            {"version": 1, "status": "promoted", "config": {"replicas": 2}},
            {"version": 2, "status": "draft", "config": {"replicas": 3}},
        ],
    }]
    revisions = Revisions()
    await initialize_mac_revision_collection(revisions)
    first = await backfill_mac_environment_revisions(
        Environments(legacy), revisions, session="transaction",
    )
    second = await backfill_mac_environment_revisions(
        Environments(legacy), revisions, session="transaction",
    )
    assert first == {"copied": 2, "already_present": 0}
    assert second == {"copied": 0, "already_present": 2}
    assert revisions.records["staging:1"]["config"] == {"replicas": 2}
    assert revisions.records["staging:2"]["status"] == "draft"
    assert len(revisions.indexes) == 2
    assert revisions.indexes[0][1]["unique"] is True


@pytest.mark.asyncio
async def test_revision_backfill_fails_closed_on_conflicting_target():
    legacy = [{
        "_id": "production",
        "environment": "production",
        "latest_version": 1,
        "versions": [{"version": 1, "status": "approved", "config": {"replicas": 2}}],
    }]
    revisions = Revisions([{
        "_id": "production:1",
        "environment": "production",
        "version": 1,
        "status": "approved",
        "config": {"replicas": 9},
    }])
    with pytest.raises(MacRevisionMigrationConflict):
        await backfill_mac_environment_revisions(
            Environments(legacy), revisions, session="transaction",
        )
    assert revisions.records["production:1"]["config"] == {"replicas": 9}


@pytest.mark.asyncio
async def test_revision_backfill_rejects_inconsistent_legacy_sequence():
    legacy = [{
        "_id": "development",
        "environment": "development",
        "latest_version": 3,
        "versions": [{"version": 1, "status": "draft", "config": {"x": 1}}],
    }]
    with pytest.raises(MacRevisionMigrationConflict):
        await backfill_mac_environment_revisions(
            Environments(legacy), Revisions(), session="transaction",
        )
