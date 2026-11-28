"""Durable, bounded, secret-redacted execution result storage."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from gridfs.asynchronous import AsyncGridFSBucket
from gridfs.errors import NoFile

from odei_api.services.project_lifecycle import fence_project_write
from odei_api.services.gridfs_upload_intents import MongoGridFSUploadIntentStore
from odei_api.services.secret_redaction import redact_secrets


class ExecutionArtifactStoreError(RuntimeError):
    """Execution result blobs and metadata could not be stored or retrieved."""


class MongoExecutionArtifactStore:
    """Keep bounded redacted stdout/stderr in GridFS with tenant-scoped metadata."""

    def __init__(self, database: Any):
        self._metadata = database["execution_artifacts"]
        self._runs = database["execution_runs"]
        self._projects = database["projects"]
        self._client = database.client
        self._stdout = AsyncGridFSBucket(database, bucket_name="execution_stdout")
        self._stderr = AsyncGridFSBucket(database, bucket_name="execution_stderr")
        self._upload_intents = MongoGridFSUploadIntentStore(database)

    async def initialize(self) -> None:
        await self._upload_intents.initialize()
        await self._metadata.create_index(
            [("organization_id", 1), ("project_id", 1), ("task_id", 1), ("run_id", 1)],
            unique=True,
        )
        await self._metadata.create_index([("created_at", -1)])
        await self._metadata.create_index([("state", 1), ("created_at", 1)])

    async def put(
        self, *, organization_id: str, project_id: str, task_id: str,
        run_id: str, exit_code: int, duration_ms: int, timed_out: bool,
        stdout: str, stderr: str, stdout_truncated: bool, stderr_truncated: bool,
    ) -> dict[str, Any]:
        for field_name, value in (
            ("organization_id", organization_id), ("project_id", project_id),
            ("task_id", task_id), ("run_id", run_id),
        ):
            if not isinstance(value, str) or not value or value != value.strip() or len(value) > 128:
                raise ValueError(f"execution artifact {field_name} is invalid")
        if isinstance(exit_code, bool) or not isinstance(exit_code, int) or not -(2 ** 31) <= exit_code <= (2 ** 32 - 1):
            raise ValueError("execution exit code is invalid")
        if isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or not 0 <= duration_ms <= 600_000:
            raise ValueError("execution duration is invalid")
        for field_name, value in (
            ("timed_out", timed_out),
            ("stdout_truncated", stdout_truncated),
            ("stderr_truncated", stderr_truncated),
        ):
            if not isinstance(value, bool):
                raise ValueError(f"execution artifact {field_name} must be boolean")
        if not isinstance(stdout, str) or not isinstance(stderr, str):
            raise TypeError("execution output must be text")
        if len(stdout.encode("utf-8")) > 1_048_576 or len(stderr.encode("utf-8")) > 1_048_576:
            raise ValueError("execution output exceeds its storage limit")
        existing = await self._metadata.find_one({
            "organization_id": organization_id, "project_id": project_id,
            "task_id": task_id, "run_id": run_id,
        })
        if existing is not None:
            return self.public_metadata(existing)
        safe_stdout = redact_secrets(stdout)
        safe_stderr = redact_secrets(stderr)
        intent_id = await self._upload_intents.create(
            organization_id=organization_id,
            project_id=project_id,
            resource_type="execution_artifact",
            bucket_names=("execution_stdout", "execution_stderr"),
        )

        stdout_id = await self._upload_intents.blob_id(
            intent_id, "execution_stdout",
        )
        stderr_id = await self._upload_intents.blob_id(
            intent_id, "execution_stderr",
        )

        async def upload_both() -> tuple[Any, Any]:
            async with self._stdout.open_upload_stream_with_id(
                stdout_id,
                f"{run_id}-stdout.txt",
                metadata={
                    "organization_id": organization_id, "project_id": project_id,
                    "run_id": run_id, "upload_intent_id": intent_id,
                },
            ) as stdout_stream:
                await stdout_stream.write(safe_stdout.encode("utf-8"))
            async with self._stderr.open_upload_stream_with_id(
                stderr_id,
                f"{run_id}-stderr.txt",
                metadata={
                    "organization_id": organization_id, "project_id": project_id,
                    "run_id": run_id, "upload_intent_id": intent_id,
                },
            ) as stderr_stream:
                await stderr_stream.write(safe_stderr.encode("utf-8"))
            return stdout_id, stderr_id

        await self._upload_intents.upload_with_heartbeat(intent_id, upload_both)
        try:
            document = {
                "_id": uuid4().hex, "organization_id": organization_id,
                "project_id": project_id, "task_id": task_id, "run_id": run_id,
                "stdout_blob_id": stdout_id, "stderr_blob_id": stderr_id,
                "exit_code": exit_code, "duration_ms": duration_ms,
                "timed_out": bool(timed_out),
                "stdout_truncated": bool(stdout_truncated),
                "stderr_truncated": bool(stderr_truncated),
                "stdout_bytes": len(safe_stdout.encode("utf-8")),
                "stderr_bytes": len(safe_stderr.encode("utf-8")),
                "created_at": datetime.now(timezone.utc),
                "state": "available",
                "upload_intent_id": intent_id,
            }
            async with self._client.start_session() as session, await session.start_transaction():
                await fence_project_write(
                    self._projects, organization_id=organization_id,
                    project_id=project_id, session=session,
                )
                await self._metadata.insert_one(document, session=session)
                await self._upload_intents.mark_committed(intent_id, session=session)
            return self.public_metadata(document)
        except Exception:
            # A lost commit acknowledgement can leave the transaction outcome
            # unknown. Preserve blobs whenever metadata may have committed;
            # deleting them would create a dangling artifact record.
            try:
                committed = await self._metadata.find_one({
                    "organization_id": organization_id,
                    "project_id": project_id,
                    "task_id": task_id,
                    "run_id": run_id,
                    "stdout_blob_id": stdout_id,
                    "stderr_blob_id": stderr_id,
                })
            except Exception:
                # An orphan can be reconciled later; a committed record must
                # never be left pointing at blobs removed by compensation.
                raise
            if committed is None:
                try:
                    await self._stdout.delete(stdout_id)
                except NoFile:
                    pass
                if stderr_id is not None:
                    try:
                        await self._stderr.delete(stderr_id)
                    except NoFile:
                        pass
            raise

    async def reconcile_upload_intents(self, *, limit: int = 100) -> int:
        return await self._upload_intents.reconcile(
            {
                "execution_stdout": self._stdout,
                "execution_stderr": self._stderr,
            },
            limit=limit,
        )

    async def get_for_tenant(
        self, *, organization_id: str, project_id: str,
        task_id: str, run_id: str,
    ) -> dict[str, Any] | None:
        document = await self._metadata.find_one({
            "organization_id": organization_id, "project_id": project_id,
            "task_id": task_id, "run_id": run_id,
            "state": {"$in": ["available", None]},
        })
        if document is None:
            return None
        try:
            stdout = await (await self._stdout.open_download_stream(document["stdout_blob_id"])).read()
            stderr = await (await self._stderr.open_download_stream(document["stderr_blob_id"])).read()
        except NoFile as exc:
            raise ExecutionArtifactStoreError("Execution artifact blob is missing") from exc
        return {
            **self.public_metadata(document),
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }

    async def delete_expired(self, *, retention_days: int = 30, limit: int = 100) -> int:
        if (
            isinstance(retention_days, bool) or not isinstance(retention_days, int)
            or not 1 <= retention_days <= 365
            or isinstance(limit, bool) or not isinstance(limit, int)
            or not 1 <= limit <= 1000
        ):
            raise ValueError("artifact retention days and batch limit must be bounded integers")
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        cursor = self._metadata.find({
            "$or": [
                {"state": "deleting"},
                {
                    "created_at": {"$lte": cutoff},
                    "state": {"$in": ["available", None]},
                },
            ],
        }).limit(limit)
        rows = await cursor.to_list(length=limit)
        deleted = 0
        for row in rows:
            # Fence the tombstone and active-run check against project deletion
            # and concurrent artifact writers in one transaction. A deleting
            # tombstone remains resumable after a process crash.
            async with self._client.start_session() as session, await session.start_transaction():
                await fence_project_write(
                    self._projects, organization_id=row["organization_id"],
                    project_id=row["project_id"], session=session, allow_deleting=True,
                )
                active_run = await self._runs.find_one({
                    "organization_id": row["organization_id"], "project_id": row["project_id"],
                    "_id": row["run_id"],
                    "status": {"$in": ["queued", "leased", "running", "collecting"]},
                }, session=session)
                if active_run is not None:
                    continue
                marked = await self._metadata.update_one(
                    {
                        "_id": row["_id"],
                        "$or": [
                            {"state": "deleting"},
                            {
                                "created_at": {"$lte": cutoff},
                                "state": {"$in": ["available", None]},
                            },
                        ],
                    },
                    {"$set": {"state": "deleting", "deleting_at": datetime.now(timezone.utc)}},
                    session=session,
                )
                if not marked.matched_count:
                    continue
            for bucket, blob_id in (
                (self._stdout, row["stdout_blob_id"]),
                (self._stderr, row["stderr_blob_id"]),
            ):
                try:
                    await bucket.delete(blob_id)
                except NoFile:
                    pass
            removed = await self._metadata.delete_one({"_id": row["_id"], "state": "deleting"})
            deleted += removed.deleted_count
        return deleted

    @staticmethod
    def public_metadata(document: dict[str, Any]) -> dict[str, Any]:
        return {
            "artifact_id": document["_id"], "run_id": document["run_id"],
            "exit_code": document["exit_code"], "duration_ms": document["duration_ms"],
            "timed_out": document["timed_out"],
            "stdout_truncated": document["stdout_truncated"],
            "stderr_truncated": document["stderr_truncated"],
            "stdout_bytes": document["stdout_bytes"],
            "stderr_bytes": document["stderr_bytes"],
            "created_at": document["created_at"].isoformat(),
        }
