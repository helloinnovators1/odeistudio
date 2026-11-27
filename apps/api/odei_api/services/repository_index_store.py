"""Tenant/project-scoped persistent repository index storage and retrieval."""
from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from pymongo.errors import DuplicateKeyError, PyMongoError

from odei_api.security.auth import Principal
from odei_api.services.audit_store import MongoAuditEventStore
from odei_api.services.project_lifecycle import fence_project_write

logger = logging.getLogger(__name__)


class RepositoryIndexStoreError(RuntimeError):
    """Persistent repository index storage is unavailable or inconsistent."""


class RepositoryIndexConflict(RepositoryIndexStoreError):
    """A concurrent index refresh changed the active project revision."""


class MongoRepositoryIndexStore:
    """Publish immutable index revisions and expose only tenant-scoped active data."""

    def __init__(self, database: Any):
        self._files = database["repository_index_files"]
        self._symbols = database["repository_index_symbols"]
        self._references = database["repository_index_references"]
        self._imports = database["repository_index_imports"]
        self._chunks = database["repository_index_chunks"]
        self._state = database["repository_index_state"]
        self._projects = database["projects"]

    async def initialize(self) -> None:
        await self._state.create_index(
            [("organization_id", 1), ("project_id", 1)], unique=True
        )
        for collection in (
            self._files, self._symbols, self._references, self._imports, self._chunks,
        ):
            await collection.create_index(
                [("organization_id", 1), ("project_id", 1), ("revision_id", 1)]
            )
            await collection.create_index([("expires_at", 1)], expireAfterSeconds=0)
        await self._files.create_index(
            [("organization_id", 1), ("project_id", 1), ("revision_id", 1), ("path", 1)],
            unique=True,
        )
        await self._symbols.create_index(
            [("organization_id", 1), ("project_id", 1), ("revision_id", 1), ("name", 1)]
        )
        await self._references.create_index(
            [("organization_id", 1), ("project_id", 1), ("revision_id", 1), ("name", 1)]
        )
        await self._imports.create_index(
            [("organization_id", 1), ("project_id", 1), ("revision_id", 1), ("module", 1)]
        )
        await self._chunks.create_index(
            [("organization_id", 1), ("project_id", 1), ("revision_id", 1), ("path", 1), ("chunk_index", 1)],
            unique=True,
        )
        await self._state.create_index([("expires_at", 1)], expireAfterSeconds=0)

    async def get_state(self, *, organization_id: str, project_id: str) -> dict[str, Any] | None:
        return await self._state.find_one({
            "organization_id": organization_id,
            "project_id": project_id,
            "expires_at": {"$gt": datetime.now(timezone.utc)},
        })

    async def get_active_files(
        self, *, organization_id: str, project_id: str, limit: int = 5_000,
    ) -> list[dict[str, Any]]:
        state = await self.get_state(organization_id=organization_id, project_id=project_id)
        if state is None:
            return []
        cursor = self._files.find({
            "organization_id": organization_id,
            "project_id": project_id,
            "revision_id": state["revision_id"],
        }, {"_id": 0}).sort("path", 1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_active_file_hashes(
        self, *, organization_id: str, project_id: str,
    ) -> dict[str, str]:
        state = await self.get_state(organization_id=organization_id, project_id=project_id)
        if state is None:
            return {}
        cursor = self._files.find({
            "organization_id": organization_id,
            "project_id": project_id,
            "revision_id": state["revision_id"],
        }, {"_id": 0, "path": 1, "sha256": 1})
        rows = await cursor.to_list(length=5_000)
        return {
            item["path"]: item["sha256"]
            for item in rows
            if isinstance(item.get("path"), str) and isinstance(item.get("sha256"), str)
        }

    async def get_active_chunks(
        self, *, organization_id: str, project_id: str, limit: int = 500,
    ) -> list[dict[str, Any]]:
        state = await self.get_state(organization_id=organization_id, project_id=project_id)
        if state is None:
            return []
        cursor = self._chunks.find({
            "organization_id": organization_id,
            "project_id": project_id,
            "revision_id": state["revision_id"],
        }, {"_id": 0}).limit(limit)
        return await cursor.to_list(length=limit)

    async def publish(
        self,
        *,
        organization_id: str,
        project_id: str,
        snapshot: dict[str, Any],
        files: list[dict[str, Any]],
        symbols: list[dict[str, Any]],
        references: list[dict[str, Any]],
        imports: list[dict[str, Any]],
        chunks: list[dict[str, Any]],
        embedding_model: str,
        chunk_limit_reached: bool,
        analysis_truncated: bool,
        mongo_client: Any,
        audit_store: MongoAuditEventStore,
        principal: Principal,
    ) -> dict[str, Any]:
        """Insert an invisible revision, then atomically publish its pointer and audit."""
        previous = await self._state.find_one({
            "organization_id": organization_id, "project_id": project_id,
        })
        previous_revision = previous.get("revision", 0) if previous else 0
        if not isinstance(previous_revision, int) or previous_revision < 0:
            raise RepositoryIndexStoreError("Stored repository index revision is invalid")
        revision = previous_revision + 1
        revision_id = uuid4().hex
        expires_at = snapshot["expires_at"]
        common = {
            "organization_id": organization_id,
            "project_id": project_id,
            "revision": revision,
            "revision_id": revision_id,
            "snapshot_id": snapshot["_id"],
            "expires_at": expires_at,
        }

        def documents(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return [{**common, **item} for item in items]

        try:
            for collection, items in (
                (self._files, files),
                (self._symbols, symbols),
                (self._references, references),
                (self._imports, imports),
                (self._chunks, chunks),
            ):
                batch = documents(items)
                for start in range(0, len(batch), 25):
                    await collection.insert_many(batch[start:start + 25], ordered=True)

            now = datetime.now(timezone.utc)
            state = {
                "organization_id": organization_id,
                "project_id": project_id,
                "revision": revision,
                "revision_id": revision_id,
                "snapshot_id": snapshot["_id"],
                "snapshot_sha256": snapshot["sha256"],
                "indexed_at": now,
                "expires_at": expires_at,
                "file_count": len(files),
                "total_bytes": sum(item["size_bytes"] for item in files),
                "symbol_count": len(symbols),
                "reference_count": len(references),
                "import_count": len(imports),
                "chunk_count": len(chunks),
                "embedding_model": embedding_model,
                "chunk_limit_reached": chunk_limit_reached,
                "analysis_truncated": analysis_truncated,
            }
            async with mongo_client.start_session() as session:
                async def transaction(active_session):
                    await fence_project_write(
                        self._projects, organization_id=organization_id,
                        project_id=project_id, session=active_session,
                    )
                    if previous is None:
                        await self._state.insert_one(state, session=active_session)
                    else:
                        result = await self._state.replace_one(
                            {
                                "organization_id": organization_id,
                                "project_id": project_id,
                                "revision": previous_revision,
                            },
                            state,
                            session=active_session,
                        )
                        if result.matched_count != 1:
                            raise RepositoryIndexConflict(
                                "Repository index changed during refresh; retry against the latest snapshot"
                            )
                    await audit_store.append(
                        organization_id=organization_id,
                        actor_issuer=principal.issuer,
                        actor_subject=principal.subject,
                        action="repository.index.refresh",
                        target_type="project",
                        target_id=project_id,
                        outcome="success",
                        request_id=uuid4().hex,
                        metadata={
                            "revision": revision,
                            "snapshot_id": snapshot["_id"],
                            "file_count": len(files),
                            "symbol_count": len(symbols),
                            "reference_count": len(references),
                            "chunk_count": len(chunks),
                            "embedding_model": embedding_model,
                        },
                        session=active_session,
                    )
                await session.with_transaction(transaction)

            if previous is not None and previous.get("revision_id"):
                retire_at = now + timedelta(hours=1)
                if isinstance(previous.get("expires_at"), datetime):
                    retire_at = min(retire_at, previous["expires_at"])
                for collection in (
                    self._files, self._symbols, self._references, self._imports, self._chunks,
                ):
                    try:
                        await collection.update_many(
                            {
                                "organization_id": organization_id,
                                "project_id": project_id,
                                "revision_id": previous["revision_id"],
                            },
                            {"$set": {"expires_at": retire_at}},
                        )
                    except PyMongoError as cleanup_error:
                        logger.warning(
                            "Could not shorten retention for superseded repository index (%s)",
                            type(cleanup_error).__name__,
                        )
            return self.public_state(state)
        except DuplicateKeyError as exc:
            await self._cleanup_unpublished_revision(
                organization_id, project_id, revision_id
            )
            raise RepositoryIndexConflict(
                "Repository index changed concurrently; retry the refresh"
            ) from exc
        except Exception:
            await self._cleanup_unpublished_revision(
                organization_id, project_id, revision_id
            )
            raise

    async def _cleanup_unpublished_revision(
        self, organization_id: str, project_id: str, revision_id: str
    ) -> None:
        """Remove orphaned build documents unless the revision became active."""
        try:
            active = await self._state.find_one({
                "organization_id": organization_id,
                "project_id": project_id,
                "revision_id": revision_id,
            })
            if active is not None:
                return
            for collection in (
                self._files, self._symbols, self._references, self._imports, self._chunks,
            ):
                await collection.delete_many({
                    "organization_id": organization_id,
                    "project_id": project_id,
                    "revision_id": revision_id,
                })
        except PyMongoError as exc:
            logger.warning(
                "Could not clean up unpublished repository index revision (%s)",
                type(exc).__name__,
            )

    async def delete_project_index(
        self, *, organization_id: str, project_id: str,
    ) -> dict[str, int]:
        """Idempotently remove every persisted index revision for one tenant project.

        Remove the active pointer first so retrieval fails closed while the
        bounded collection cleanup proceeds. Every deletion is tenant/project
        scoped; retrying after a partial storage failure completes the cleanup.
        """
        if not organization_id or not project_id:
            raise ValueError("organization_id and project_id are required")
        state_result = await self._state.delete_one({
            "organization_id": organization_id,
            "project_id": project_id,
        })
        deleted = {"state": state_result.deleted_count}
        for name, collection in (
            ("files", self._files),
            ("symbols", self._symbols),
            ("references", self._references),
            ("imports", self._imports),
            ("chunks", self._chunks),
        ):
            result = await collection.delete_many({
                "organization_id": organization_id,
                "project_id": project_id,
            })
            deleted[name] = result.deleted_count
        return deleted

    @staticmethod
    def public_state(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "organization_id": state["organization_id"],
            "project_id": state["project_id"],
            "revision": state["revision"],
            "snapshot_id": state["snapshot_id"],
            "snapshot_sha256": state["snapshot_sha256"],
            "indexed_at": state["indexed_at"].isoformat(),
            "expires_at": state["expires_at"].isoformat(),
            "file_count": state["file_count"],
            "total_bytes": state["total_bytes"],
            "symbol_count": state["symbol_count"],
            "reference_count": state["reference_count"],
            "import_count": state["import_count"],
            "chunk_count": state["chunk_count"],
            "embedding_model": state["embedding_model"],
            "chunk_limit_reached": state["chunk_limit_reached"],
            "analysis_truncated": state.get("analysis_truncated", False),
        }

    async def search_semantic(
        self, *, organization_id: str, project_id: str,
        query_embedding: list[float], limit: int = 10,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 50 or not query_embedding:
            raise ValueError("semantic search parameters are invalid")
        chunks = await self.get_active_chunks(
            organization_id=organization_id, project_id=project_id
        )
        if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in query_embedding):
            raise ValueError("query embedding is invalid")
        query_norm = math.sqrt(sum(value * value for value in query_embedding))
        if query_norm == 0:
            raise ValueError("query embedding is invalid")
        scored = []
        for chunk in chunks:
            vector = chunk.get("embedding")
            if (
                not isinstance(vector, list) or len(vector) != len(query_embedding)
                or any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in vector)
            ):
                continue
            norm = math.sqrt(sum(value * value for value in vector))
            if norm == 0:
                continue
            score = sum(a * b for a, b in zip(query_embedding, vector)) / (query_norm * norm)
            scored.append({
                "path": chunk["path"],
                "line_start": chunk["line_start"],
                "snippet": chunk["text"][:500],
                "score": round(score, 6),
                "sha256": chunk["sha256"],
                "revision": chunk["revision"],
                "snapshot_id": chunk["snapshot_id"],
            })
        return sorted(scored, key=lambda item: item["score"], reverse=True)[:limit]

    async def search_symbols(
        self, *, organization_id: str, project_id: str, name: str, limit: int = 50,
    ) -> list[dict[str, Any]]:
        state = await self.get_state(organization_id=organization_id, project_id=project_id)
        if state is None:
            return []
        cursor = self._symbols.find({
            "organization_id": organization_id, "project_id": project_id,
            "revision_id": state["revision_id"],
            "name": {"$regex": re.escape(name), "$options": "i"},
        }, {"_id": 0}).sort("path", 1).limit(limit)
        return await cursor.to_list(length=limit)

    async def search_references(
        self, *, organization_id: str, project_id: str, name: str, limit: int = 100,
    ) -> list[dict[str, Any]]:
        state = await self.get_state(organization_id=organization_id, project_id=project_id)
        if state is None:
            return []
        cursor = self._references.find({
            "organization_id": organization_id, "project_id": project_id,
            "revision_id": state["revision_id"],
            "name": {"$regex": "^" + re.escape(name) + "$"},
        }, {"_id": 0}).sort("path", 1).limit(limit)
        return await cursor.to_list(length=limit)

    async def dependency_graph(
        self, *, organization_id: str, project_id: str, limit: int = 2_000,
    ) -> dict[str, Any]:
        state = await self.get_state(organization_id=organization_id, project_id=project_id)
        if state is None:
            return {"revision": None, "nodes": [], "edges": []}
        cursor = self._imports.find({
            "organization_id": organization_id, "project_id": project_id,
            "revision_id": state["revision_id"],
        }, {"_id": 0}).sort("path", 1).limit(limit)
        imports = await cursor.to_list(length=limit)
        nodes = sorted({
            value for item in imports for value in (item["path"], item["module"])
        })
        return {
            "revision": state["revision"],
            "nodes": nodes,
            "snapshot_id": state["snapshot_id"],
            "edges": [{
                "source": item["path"], "target": item["module"],
                "sha256": item["sha256"], "revision": state["revision"],
                "snapshot_id": state["snapshot_id"],
            } for item in imports],
        }
