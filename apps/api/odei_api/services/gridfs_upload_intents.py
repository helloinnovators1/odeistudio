"""Crash-recoverable ownership records for GridFS uploads.

Every upload creates a tenant-fenced intent before writing any GridFS bytes.
GridFS files carry the intent ID. The metadata transaction that publishes the
resource also changes the intent to committed. Reconciliation only deletes
files for expired, uncommitted intents; committed intents are metadata-only
garbage and are never used as a reason to delete blobs.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from gridfs.errors import NoFile

from odei_api.services.project_lifecycle import fence_project_write


LEASE_SECONDS = 300
HEARTBEAT_SECONDS = 30
RECONCILE_GRACE_SECONDS = 120
COMMITTED_INTENT_RETENTION = timedelta(days=1)
RESOURCE_BUCKETS = {
    "workspace_snapshot": ("workspace_snapshot_blobs",),
    "execution_artifact": ("execution_stdout", "execution_stderr"),
}
ALLOWED_BUCKETS = frozenset(
    bucket for bucket_names in RESOURCE_BUCKETS.values() for bucket in bucket_names
)


class UploadIntentLeaseLost(RuntimeError):
    """The upload lost its renewable ownership lease."""


class MongoGridFSUploadIntentStore:
    """Durable lease, commit and restart-reconciliation protocol for GridFS."""

    def __init__(self, database: Any):
        self._database = database
        self._collection = database["gridfs_upload_intents"]
        self._client = database.client
        self._projects = database["projects"]

    async def initialize(self) -> None:
        await self._collection.create_index(
            [("resource_type", 1), ("state", 1), ("lease_expires_at", 1)]
        )
        await self._collection.create_index(
            [("resource_type", 1), ("state", 1), ("committed_at", 1)]
        )
        await self._collection.create_index(
            [("organization_id", 1), ("project_id", 1), ("state", 1)]
        )

    async def create(
        self, *, organization_id: str, project_id: str,
        resource_type: str, bucket_names: tuple[str, ...],
    ) -> str:
        expected_buckets = RESOURCE_BUCKETS.get(resource_type)
        if expected_buckets is None or tuple(bucket_names) != expected_buckets:
            raise ValueError("upload intent resource type and GridFS buckets do not match")
        intent_id = uuid4().hex
        now = datetime.now(timezone.utc)
        document = {
            "_id": intent_id,
            "organization_id": organization_id,
            "project_id": project_id,
            "resource_type": resource_type,
            "bucket_names": list(bucket_names),
            "blob_ids": {name: uuid4().hex for name in bucket_names},
            "state": "uploading",
            "created_at": now,
            "heartbeat_at": now,
            "lease_expires_at": now + timedelta(seconds=LEASE_SECONDS),
        }
        async with self._client.start_session() as session, await session.start_transaction():
            await fence_project_write(
                self._projects, organization_id=organization_id,
                project_id=project_id, session=session,
            )
            await self._collection.insert_one(document, session=session)
        return intent_id

    async def blob_id(self, intent_id: str, bucket_name: str) -> str:
        if bucket_name not in ALLOWED_BUCKETS:
            raise ValueError("unsupported GridFS bucket")
        intent = await self._collection.find_one(
            {
                "_id": intent_id,
                "state": "uploading",
                "lease_expires_at": {"$gt": datetime.now(timezone.utc)},
            }
        )
        if intent is None or bucket_name not in intent.get("blob_ids", {}):
            raise UploadIntentLeaseLost("GridFS upload intent is unavailable")
        return intent["blob_ids"][bucket_name]

    async def _renew_lease(self, intent_id: str) -> None:
        """Renew only an unexpired upload lease; never resurrect stale ownership."""
        now = datetime.now(timezone.utc)
        result = await self._collection.update_one(
            {
                "_id": intent_id,
                "state": "uploading",
                "lease_expires_at": {"$gt": now},
            },
            {
                "$set": {
                    "heartbeat_at": now,
                    "lease_expires_at": now + timedelta(seconds=LEASE_SECONDS),
                },
            },
        )
        if result.matched_count != 1:
            raise UploadIntentLeaseLost("GridFS upload intent lease was lost")

    async def _heartbeat(self, intent_id: str) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            await self._renew_lease(intent_id)

    async def upload_with_heartbeat(
        self, intent_id: str, upload: Callable[[], Awaitable[Any]],
    ) -> Any:
        # Establish live ownership before opening a GridFS stream. A delayed
        # caller must not start writing against an expired/reaped intent.
        await self._renew_lease(intent_id)
        upload_task = asyncio.create_task(upload())
        heartbeat_task = asyncio.create_task(self._heartbeat(intent_id))
        try:
            done, _ = await asyncio.wait(
                {upload_task, heartbeat_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if heartbeat_task in done:
                error = heartbeat_task.exception()
                if error is None:
                    error = UploadIntentLeaseLost("GridFS upload heartbeat stopped")
                upload_task.cancel()
                await asyncio.gather(upload_task, return_exceptions=True)
                raise error
            return await upload_task
        finally:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)

    async def mark_committed(self, intent_id: str, *, session: Any) -> None:
        now = datetime.now(timezone.utc)
        result = await self._collection.update_one(
            {
                "_id": intent_id,
                "state": "uploading",
                "lease_expires_at": {"$gt": now},
            },
            {
                "$set": {"state": "committed", "committed_at": now},
                "$unset": {"lease_expires_at": "", "heartbeat_at": ""},
            },
            session=session,
        )
        if result.matched_count != 1:
            raise UploadIntentLeaseLost("GridFS upload intent could not be committed")

    async def reconcile(
        self, buckets: dict[str, Any], *, limit: int = 100,
        resource_type: str | None = None,
    ) -> int:
        """Resume deleting intents and reap expired uploads in bounded batches."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("upload-intent reconciliation limit must be between 1 and 1000")
        if resource_type is not None:
            expected_buckets = RESOURCE_BUCKETS.get(resource_type)
            if expected_buckets is None or set(buckets) != set(expected_buckets):
                raise ValueError("upload-intent reconciler resource type and buckets do not match")
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(seconds=RECONCILE_GRACE_SECONDS)
        committed_before = now - COMMITTED_INTENT_RETENTION
        query = {
            "$or": [
                {"state": "deleting"},
                {"state": "uploading", "lease_expires_at": {"$lte": stale_before}},
                {"state": "committed", "committed_at": {"$lte": committed_before}},
            ],
        }
        if resource_type is not None:
            query["resource_type"] = resource_type
        # Keep deleting tombstones after a successful sweep. A process can be
        # paused beyond its lease and later resume a GridFS stream; recurring
        # sweeps must therefore remain able to remove chunks written after an
        # earlier cleanup pass. Oldest cleanup timestamps rotate bounded batches.
        cursor = self._collection.find(query).sort("last_cleanup_at", 1).limit(limit)
        intents = await cursor.to_list(length=limit)
        reconciled = 0
        for intent in intents:
            intent_id = intent["_id"]
            if intent.get("state") == "committed":
                await self._collection.delete_one({"_id": intent_id, "state": "committed"})
                reconciled += 1
                continue
            if intent.get("state") == "uploading":
                claimed = await self._collection.update_one(
                    {
                        "_id": intent_id,
                        "state": "uploading",
                        "lease_expires_at": {"$lte": stale_before},
                    },
                    {"$set": {"state": "deleting", "deleting_at": now}},
                )
                if claimed.matched_count != 1:
                    continue
                intent["state"] = "deleting"
            for bucket_name in intent.get("bucket_names", []):
                if bucket_name not in ALLOWED_BUCKETS or bucket_name not in buckets:
                    raise RuntimeError("upload intent references an unsupported GridFS bucket")
                blob_id = intent.get("blob_ids", {}).get(bucket_name)
                if blob_id is not None:
                    # The file ID is persisted before the upload begins. This
                    # also removes chunks left by a process crash before GridFS
                    # could publish the corresponding .files document.
                    await self._database[f"{bucket_name}.chunks"].delete_many(
                        {"files_id": blob_id}
                    )
                    await self._database[f"{bucket_name}.files"].delete_one(
                        {"_id": blob_id}
                    )
                else:
                    # Compatibility for intents written before deterministic
                    # file IDs were introduced.
                    files = await self._database[f"{bucket_name}.files"].find(
                        {"metadata.upload_intent_id": intent_id},
                        {"_id": 1},
                    ).to_list(length=10_000)
                    for file_document in files:
                        try:
                            await buckets[bucket_name].delete(file_document["_id"])
                        except NoFile:
                            pass
            await self._collection.update_one(
                {"_id": intent_id, "state": "deleting"},
                {
                    "$set": {"last_cleanup_at": datetime.now(timezone.utc)},
                    "$inc": {"cleanup_passes": 1},
                },
            )
            reconciled += 1
        return reconciled
