"""Durable, bounded, secret-redacted execution result storage."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from gridfs.errors import NoFile
from gridfs.asynchronous import AsyncGridFSBucket

from odei_api.services.secret_redaction import redact_secrets


class ExecutionArtifactStoreError(RuntimeError):
    """Execution result blobs and metadata could not be stored or retrieved."""


class MongoExecutionArtifactStore:
    """Keep bounded redacted stdout/stderr in GridFS with tenant-scoped metadata."""

    def __init__(self, database: Any):
        self._metadata = database["execution_artifacts"]
        self._runs = database["execution_runs"]
        self._stdout = AsyncGridFSBucket(database, bucket_name="execution_stdout")
        self._stderr = AsyncGridFSBucket(database, bucket_name="execution_stderr")

    async def initialize(self) -> None:
        await self._metadata.create_index(
            [("organization_id", 1), ("project_id", 1), ("task_id", 1), ("run_id", 1)],
            unique=True,
        )
        await self._metadata.create_index([("created_at", -1)])

    async def put(
        self, *, organization_id: str, project_id: str, task_id: str,
        run_id: str, exit_code: int, duration_ms: int, timed_out: bool,
        stdout: str, stderr: str, stdout_truncated: bool, stderr_truncated: bool,
    ) -> dict[str, Any]:
        if not isinstance(stdout, str) or not isinstance(stderr, str):
            raise ValueError("execution output must be text")
        if len(stdout.encode("utf-8")) > 1_048_576 or len(stderr.encode("utf-8")) > 1_048_576:
            raise ValueError("execution output exceeds its storage limit")
        if not 0 <= duration_ms <= 600_000:
            raise ValueError("execution duration is invalid")
        existing = await self._metadata.find_one({
            "organization_id": organization_id, "project_id": project_id,
            "task_id": task_id, "run_id": run_id,
        })
        if existing is not None:
            return self.public_metadata(existing)
        safe_stdout = redact_secrets(stdout)
        safe_stderr = redact_secrets(stderr)
        stdout_id = await self._stdout.upload_from_stream(
            f"{run_id}-stdout.txt", safe_stdout.encode("utf-8"),
            metadata={"organization_id": organization_id, "run_id": run_id},
        )
        stderr_id = None
        try:
            stderr_id = await self._stderr.upload_from_stream(
                f"{run_id}-stderr.txt", safe_stderr.encode("utf-8"),
                metadata={"organization_id": organization_id, "run_id": run_id},
            )
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
            }
            await self._metadata.insert_one(document)
            return self.public_metadata(document)
        except Exception:
            await self._stdout.delete(stdout_id)
            if stderr_id is not None:
                await self._stderr.delete(stderr_id)
            raise

    async def get_for_tenant(
        self, *, organization_id: str, project_id: str,
        task_id: str, run_id: str,
    ) -> dict[str, Any] | None:
        document = await self._metadata.find_one({
            "organization_id": organization_id, "project_id": project_id,
            "task_id": task_id, "run_id": run_id,
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
        if not 1 <= retention_days <= 365 or not 1 <= limit <= 1000:
            raise ValueError("artifact retention policy is invalid")
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        cursor = self._metadata.find({"created_at": {"$lte": cutoff}}).limit(limit)
        rows = await cursor.to_list(length=limit)
        deleted = 0
        for row in rows:
            active_run = await self._runs.find_one({
                "organization_id": row["organization_id"], "_id": row["run_id"],
                "status": {"$in": ["queued", "leased", "running", "collecting"]},
            })
            if active_run is not None:
                continue
            await self._stdout.delete(row["stdout_blob_id"])
            await self._stderr.delete(row["stderr_blob_id"])
            await self._metadata.delete_one({"_id": row["_id"], "created_at": {"$lte": cutoff}})
            deleted += 1
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
