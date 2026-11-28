"""Tenant-scoped GridFS storage for immutable workspace snapshot archives."""
from __future__ import annotations

import io
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from gridfs.asynchronous import AsyncGridFSBucket
from gridfs.errors import NoFile

from odei_api.services.project_lifecycle import fence_project_write
from odei_api.services.gridfs_upload_intents import MongoGridFSUploadIntentStore


_MAX_ARCHIVE_BYTES = 50 * 1024 * 1024


class SnapshotStoreError(RuntimeError):
    """Snapshot object storage is unavailable or inconsistent."""


class MongoWorkspaceSnapshotStore:
    """Store bounded ZIP archives in GridFS with tenant-scoped metadata."""

    def __init__(self, database: Any):
        self._metadata = database["workspace_snapshots"]
        self._projects = database["projects"]
        self._client = database.client
        self._runs = database["execution_runs"]
        self._bucket = AsyncGridFSBucket(database, bucket_name="workspace_snapshot_blobs")
        self._upload_intents = MongoGridFSUploadIntentStore(database)

    async def initialize(self) -> None:
        await self._upload_intents.initialize()
        await self._metadata.create_index(
            [("organization_id", 1), ("project_id", 1), ("created_at", -1)]
        )
        await self._metadata.create_index(
            [("organization_id", 1), ("task_id", 1), ("created_at", -1)]
        )
        await self._metadata.create_index([("expires_at", 1)])

    async def put(
        self, *, organization_id: str, project_id: str, task_id: str,
        owner_issuer: str, owner_subject: str, archive: bytes,
        sha256: str, file_count: int, total_bytes: int,
        retention_days: int = 7,
    ) -> dict[str, Any]:
        if isinstance(retention_days, bool) or not isinstance(retention_days, int) or not 1 <= retention_days <= 30:
            raise ValueError("snapshot retention must be an integer between 1 and 30 days")
        if not isinstance(archive, bytes) or not archive:
            raise ValueError("snapshot archive must be non-empty bytes")
        if len(archive) > _MAX_ARCHIVE_BYTES:
            raise ValueError("snapshot archive exceeds the 50 MiB storage limit")
        for field_name, value in (
            ("organization_id", organization_id), ("project_id", project_id),
            ("task_id", task_id), ("owner_issuer", owner_issuer),
            ("owner_subject", owner_subject),
        ):
            if not isinstance(value, str) or not value or value != value.strip() or len(value) > 128:
                raise ValueError(f"snapshot {field_name} is invalid")
        if not isinstance(sha256, str) or re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
            raise ValueError("snapshot manifest SHA-256 must be 64 lowercase hexadecimal characters")
        if isinstance(file_count, bool) or not isinstance(file_count, int) or not 0 <= file_count <= 10_000:
            raise ValueError("snapshot file count is invalid")
        if isinstance(total_bytes, bool) or not isinstance(total_bytes, int) or not 0 <= total_bytes <= 512 * 1024 * 1024:
            raise ValueError("snapshot expanded byte count is invalid")
        snapshot_id = uuid4().hex
        now = datetime.now(timezone.utc)
        intent_id = await self._upload_intents.create(
            organization_id=organization_id,
            project_id=project_id,
            resource_type="workspace_snapshot",
            bucket_names=("workspace_snapshot_blobs",),
        )
        blob_id = await self._upload_intents.upload_with_heartbeat(
            intent_id,
            lambda: self._bucket.upload_from_stream(
                f"{snapshot_id}.zip", io.BytesIO(archive),
                metadata={
                    "snapshot_id": snapshot_id,
                    "organization_id": organization_id,
                    "project_id": project_id,
                    "task_id": task_id,
                    "sha256": sha256,
                    "upload_intent_id": intent_id,
                },
            ),
        )
        document = {
            "_id": snapshot_id,
            "organization_id": organization_id,
            "project_id": project_id,
            "task_id": task_id,
            "owner_issuer": owner_issuer,
            "owner_subject": owner_subject,
            "blob_id": blob_id,
            "sha256": sha256,
            "file_count": file_count,
            "total_bytes": total_bytes,
            "archive_bytes": len(archive),
            "created_at": now,
            "expires_at": now + timedelta(days=retention_days),
            "state": "available",
            "upload_intent_id": intent_id,
        }
        try:
            async with self._client.start_session() as session, await session.start_transaction():
                await fence_project_write(
                    self._projects, organization_id=organization_id,
                    project_id=project_id, session=session,
                )
                await self._metadata.insert_one(document, session=session)
                await self._upload_intents.mark_committed(intent_id, session=session)
        except Exception:
            # A transaction commit can have an unknown outcome when the
            # connection drops after MongoDB commits. Never compensate-delete
            # a blob until the metadata lookup proves it is unreferenced.
            try:
                committed = await self._metadata.find_one({
                    "_id": snapshot_id,
                    "organization_id": organization_id,
                    "project_id": project_id,
                    "blob_id": blob_id,
                })
            except Exception:
                # Preserve the blob when metadata state cannot be established;
                # an orphan is recoverable, a dangling committed reference is not.
                raise
            if committed is None:
                try:
                    await self._bucket.delete(blob_id)
                except NoFile:
                    pass
            raise
        return self.public_metadata(document)

    async def get_for_tenant(
        self, *, organization_id: str, project_id: str, snapshot_id: str,
    ) -> dict[str, Any] | None:
        return await self._metadata.find_one({
            "_id": snapshot_id, "organization_id": organization_id,
            "project_id": project_id, "state": "available",
            "expires_at": {"$gt": datetime.now(timezone.utc)},
        })

    async def get_latest_for_tenant(
        self, *, organization_id: str, project_id: str,
    ) -> dict[str, Any] | None:
        """Return the newest unexpired snapshot for one authorized project."""
        return await self._metadata.find_one(
            {
                "organization_id": organization_id,
                "project_id": project_id,
                "state": "available",
                "expires_at": {"$gt": datetime.now(timezone.utc)},
            },
            sort=[("created_at", -1)],
        )

    async def get_archive_for_worker(self, *, snapshot_id: str) -> tuple[dict[str, Any], bytes] | None:
        document = await self._metadata.find_one({
            "_id": snapshot_id, "state": "available",
            "expires_at": {"$gt": datetime.now(timezone.utc)},
        })
        if document is None:
            return None
        try:
            stream = await self._bucket.open_download_stream(document["blob_id"])
            archive = await stream.read()
        except NoFile as exc:
            raise SnapshotStoreError("Snapshot blob is missing") from exc
        if len(archive) != document["archive_bytes"]:
            raise SnapshotStoreError("Snapshot blob size does not match metadata")
        return document, archive

    async def delete_for_tenant(self, *, organization_id: str, project_id: str, snapshot_id: str) -> bool:
        document = await self._metadata.find_one({
            "_id": snapshot_id, "organization_id": organization_id,
            "project_id": project_id,
        })
        if document is None:
            return False
        async with self._client.start_session() as session, await session.start_transaction():
            await fence_project_write(
                self._projects, organization_id=organization_id,
                project_id=project_id, session=session, allow_deleting=True,
            )
            active_run = await self._runs.find_one(
                {"organization_id": organization_id, "project_id": project_id,
                 "snapshot_id": snapshot_id,
                 "status": {"$in": ["queued", "leased", "running", "collecting"]}},
                session=session,
            )
            if active_run is not None:
                return False
            await self._metadata.update_one(
                {"_id": snapshot_id, "organization_id": organization_id,
                 "project_id": project_id},
                {"$set": {"state": "deleting", "deleting_at": datetime.now(timezone.utc)}},
                session=session,
            )
        try:
            await self._bucket.delete(document["blob_id"])
        except NoFile:
            pass
        await self._metadata.delete_one({
            "_id": snapshot_id, "organization_id": organization_id,
            "project_id": project_id, "state": "deleting",
        })
        return True

    async def delete_expired(self, *, limit: int = 100) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("deletion batch limit must be an integer between 1 and 1000")
        now = datetime.now(timezone.utc)
        cursor = self._metadata.find({
            "$or": [
                {"state": "deleting"},
                {"expires_at": {"$lte": now}},
            ],
        }).limit(limit)
        rows = await cursor.to_list(length=limit)
        deleted = 0
        for row in rows:
            async with self._client.start_session() as session, await session.start_transaction():
                await fence_project_write(
                    self._projects, organization_id=row["organization_id"],
                    project_id=row["project_id"], session=session, allow_deleting=True,
                )
                active_run = await self._runs.find_one(
                    {"organization_id": row["organization_id"], "project_id": row["project_id"],
                     "snapshot_id": row["_id"],
                     "status": {"$in": ["queued", "leased", "running", "collecting"]}},
                    session=session,
                )
                if active_run is not None:
                    continue
                marked = await self._metadata.update_one(
                    {"_id": row["_id"],
                     "state": {"$in": ["available", "deleting"]},
                     "$or": [
                         {"state": "deleting"},
                         {"expires_at": {"$lte": now}},
                     ]},
                    {"$set": {"state": "deleting", "deleting_at": now}},
                    session=session,
                )
                if not marked.matched_count:
                    continue
            try:
                await self._bucket.delete(row["blob_id"])
            except NoFile:
                pass
            removed = await self._metadata.delete_one({
                "_id": row["_id"], "organization_id": row["organization_id"],
                "project_id": row["project_id"], "state": "deleting",
            })
            deleted += removed.deleted_count
        return deleted

    @staticmethod
    def public_metadata(document: dict[str, Any]) -> dict[str, Any]:
        return {
            "snapshot_id": document["_id"],
            "organization_id": document["organization_id"],
            "project_id": document["project_id"],
            "task_id": document["task_id"],
            "sha256": document["sha256"],
            "file_count": document["file_count"],
            "total_bytes": document["total_bytes"],
            "archive_bytes": document["archive_bytes"],
            "created_at": document["created_at"].isoformat(),
            "expires_at": document["expires_at"].isoformat(),
        }
