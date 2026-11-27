"""Tenant-scoped GridFS storage for immutable workspace snapshot archives."""
from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from gridfs.asynchronous import AsyncGridFSBucket
from gridfs.errors import NoFile

from odei_api.services.project_lifecycle import fence_project_write


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

    async def initialize(self) -> None:
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
        if not 1 <= retention_days <= 30:
            raise ValueError("snapshot retention must be between 1 and 30 days")
        snapshot_id = uuid4().hex
        now = datetime.now(timezone.utc)
        blob_id = await self._bucket.upload_from_stream(
            f"{snapshot_id}.zip", io.BytesIO(archive),
            metadata={
                "snapshot_id": snapshot_id,
                "organization_id": organization_id,
                "project_id": project_id,
                "task_id": task_id,
                "sha256": sha256,
            },
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
        }
        try:
            async with self._client.start_session() as session, await session.start_transaction():
                await fence_project_write(
                    self._projects, organization_id=organization_id,
                    project_id=project_id, session=session,
                )
                await self._metadata.insert_one(document, session=session)
        except Exception:
            await self._bucket.delete(blob_id)
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
                {"snapshot_id": snapshot_id,
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
        if not 1 <= limit <= 1000:
            raise ValueError("deletion batch limit is invalid")
        now = datetime.now(timezone.utc)
        cursor = self._metadata.find({"expires_at": {"$lte": now}}).limit(limit)
        rows = await cursor.to_list(length=limit)
        deleted = 0
        for row in rows:
            async with self._client.start_session() as session, await session.start_transaction():
                await fence_project_write(
                    self._projects, organization_id=row["organization_id"],
                    project_id=row["project_id"], session=session, allow_deleting=True,
                )
                active_run = await self._runs.find_one(
                    {"snapshot_id": row["_id"],
                     "status": {"$in": ["queued", "leased", "running", "collecting"]}},
                    session=session,
                )
                if active_run is not None:
                    continue
                marked = await self._metadata.update_one(
                    {"_id": row["_id"], "expires_at": {"$lte": now},
                     "state": {"$in": ["available", "deleting"]}},
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
