"""Authenticated, tenant-scoped NEXUS repository indexing and retrieval API."""
from __future__ import annotations

import logging
import re
from tempfile import TemporaryDirectory
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import Path as ApiPath
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from pymongo.errors import PyMongoError
from starlette.concurrency import run_in_threadpool

from odei_api.config import get_settings
from odei_api.model_client import ModelConfigurationError
from odei_api.security.auth import (
    Principal,
    get_current_principal,
    require_organization_membership,
)
from odei_api.services.project_access import require_project_access
from odei_api.services.repository_analysis import analyze_repository
from odei_api.services.repository_index import RepositoryIndex, RepositoryIndexError
from odei_api.services.repository_index_store import (
    MongoRepositoryIndexStore,
    RepositoryIndexConflict,
)
from odei_api.services.workspace_snapshots import SnapshotError, WorkspaceSnapshotIngestor

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()
principal_dependency = Depends(get_current_principal)
_EMBEDDING_MODEL = "text-embedding-3-small"
_MAX_SEMANTIC_CHUNKS = 500
_EMBEDDING_BATCH_SIZE = 64


class RepositoryIndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cloud_embedding_consent: StrictBool


class SemanticSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=512)
    cloud_model_consent: StrictBool
    limit: int = Field(default=10, ge=1, le=50)


def _database(request: Request):
    database = getattr(request.app.state, "mongo_database", None)
    if database is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "REPOSITORY_STORE_UNAVAILABLE", "message": "Repository intelligence storage is not configured."},
        )
    return database


async def _authorize(
    request: Request, principal: Principal, organization_id: str, project_id: str,
) -> dict:
    if organization_id != organization_id.strip() or project_id != project_id.strip():
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_RESOURCE_ID", "message": "Resource identifier is invalid."},
        )
    database = _database(request)
    try:
        await require_organization_membership(
            database["organization_memberships"],
            principal=principal,
            organization_id=organization_id,
        )
        return await require_project_access(
            database["projects"], database["project_memberships"],
            organization_id=organization_id, project_id=project_id,
            identity_issuer=principal.issuer, identity_subject=principal.subject,
        )
    except PyMongoError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "PROJECT_STORE_UNAVAILABLE", "message": "Project authorization is temporarily unavailable."},
        ) from exc


async def _audit(
    request: Request, principal: Principal, organization_id: str, project_id: str,
    action: str, metadata: dict,
) -> None:
    store = getattr(request.app.state, "audit_event_store", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Repository access audit storage is unavailable."},
        )
    try:
        await store.append(
            organization_id=organization_id,
            actor_issuer=principal.issuer,
            actor_subject=principal.subject,
            action=action,
            target_type="project",
            target_id=project_id,
            outcome="success",
            request_id=uuid4().hex,
            metadata=metadata,
        )
    except Exception as exc:
        logger.error("Repository intelligence audit failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Repository access could not be audited."},
        ) from exc


def _embedding_batch(client: OpenAI, texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model=_EMBEDDING_MODEL, input=texts)
    rows = sorted(response.data, key=lambda item: item.index)
    return [list(item.embedding) for item in rows]


async def _embed_new_chunks(
    chunks: list[dict], existing_chunks: list[dict], *, client: OpenAI | None,
) -> list[dict]:
    existing = {
        (item.get("path"), item.get("chunk_index"), item.get("sha256")): item.get("embedding")
        for item in existing_chunks
    }
    missing: list[dict] = []
    for chunk in chunks:
        key = (chunk["path"], chunk["chunk_index"], chunk["sha256"])
        vector = existing.get(key)
        if not (isinstance(vector, list) and len(vector) == 1536):
            missing.append(chunk)
    if missing and client is None:
        raise ModelConfigurationError("Embedding API key is not configured")
    embedded: dict[tuple[str, int, str], list[float]] = {}
    for start in range(0, len(missing), _EMBEDDING_BATCH_SIZE):
        batch = missing[start:start + _EMBEDDING_BATCH_SIZE]
        vectors = await run_in_threadpool(
            _embedding_batch, client, [item["text"] for item in batch]
        )
        if len(vectors) != len(batch) or any(len(vector) != 1536 for vector in vectors):
            raise RuntimeError("Embedding provider returned an unexpected vector shape")
        for item, vector in zip(batch, vectors, strict=True):
            embedded[(item["path"], item["chunk_index"], item["sha256"])] = vector
    result: list[dict] = []
    for chunk in chunks:
        key = (chunk["path"], chunk["chunk_index"], chunk["sha256"])
        vector = existing.get(key)
        if not isinstance(vector, list) or len(vector) != 1536:
            vector = embedded[key]
        result.append({**chunk, "embedding": vector})
    return result


def _active_state_response(state: dict | None) -> dict:
    if state is None:
        return {"indexed": False}
    return {"indexed": True, **MongoRepositoryIndexStore.public_state(state)}


@router.get(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/repository-index",
    tags=["repository-intelligence"],
)
async def get_repository_index_state(
    request: Request,
    organization_id: str = ApiPath(min_length=1, max_length=128),
    project_id: str = ApiPath(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    await _authorize(request, principal, organization_id, project_id)
    store = getattr(request.app.state, "repository_index_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={"code": "REPOSITORY_STORE_UNAVAILABLE"})
    try:
        state = await store.get_state(organization_id=organization_id, project_id=project_id)
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "REPOSITORY_STORE_UNAVAILABLE"}) from exc
    await _audit(
        request, principal, organization_id, project_id,
        "repository.index.read", {"indexed": state is not None},
    )
    return _active_state_response(state)


@router.post(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/repository-index",
    tags=["repository-intelligence"],
)
async def refresh_repository_index(
    payload: RepositoryIndexRequest,
    request: Request,
    organization_id: str = ApiPath(min_length=1, max_length=128),
    project_id: str = ApiPath(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    if payload.cloud_embedding_consent is not True:
        raise HTTPException(
            status_code=400,
            detail={"code": "CLOUD_EMBEDDING_CONSENT_REQUIRED", "message": "Explicit consent is required before sending repository excerpts to the embedding provider."},
        )
    await _authorize(request, principal, organization_id, project_id)
    store = getattr(request.app.state, "repository_index_store", None)
    snapshots = getattr(request.app.state, "workspace_snapshot_store", None)
    mongo_client = getattr(request.app.state, "mongo_client", None)
    audit_store = getattr(request.app.state, "audit_event_store", None)
    if store is None or snapshots is None or mongo_client is None or audit_store is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "REPOSITORY_STORE_UNAVAILABLE", "message": "Repository indexing dependencies are not configured."},
        )
    try:
        snapshot = await snapshots.get_latest_for_tenant(
            organization_id=organization_id, project_id=project_id,
        )
        if snapshot is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "WORKSPACE_SNAPSHOT_NOT_FOUND", "message": "No active workspace snapshot exists for this project."},
            )
        downloaded = await snapshots.get_archive_for_worker(snapshot_id=snapshot["_id"])
        if downloaded is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "WORKSPACE_SNAPSHOT_NOT_FOUND", "message": "The project workspace snapshot is no longer available."},
            )
        archive_metadata, archive = downloaded
        if (
            archive_metadata.get("organization_id") != organization_id
            or archive_metadata.get("project_id") != project_id
            or archive_metadata.get("_id") != snapshot.get("_id")
        ):
            raise HTTPException(
                status_code=404,
                detail={"code": "WORKSPACE_SNAPSHOT_NOT_FOUND", "message": "The project workspace snapshot is not available."},
            )

        await _audit(
            request, principal, organization_id, project_id,
            "repository.index.refresh.started",
            {"snapshot_id": snapshot["_id"], "archive_bytes": len(archive)},
        )
        previous_hashes = await store.get_active_file_hashes(
            organization_id=organization_id, project_id=project_id,
        )
        with TemporaryDirectory(prefix="odei-repository-index-") as temporary_root:
            ingestor = WorkspaceSnapshotIngestor(
                temporary_root, max_archive_bytes=50 * 1024 * 1024,
                max_files=5_000, max_file_bytes=1_048_576,
                max_total_bytes=64 * 1024 * 1024,
            )
            snapshot_record = await run_in_threadpool(ingestor.ingest, archive)
            if snapshot_record.sha256 != snapshot["sha256"]:
                raise SnapshotError("Snapshot manifest digest did not match its stored metadata")
            index = RepositoryIndex(
                snapshot_record.path, max_files=5_000,
                max_file_bytes=1_048_576, max_total_bytes=64 * 1024 * 1024,
            )
            update = await run_in_threadpool(index.rebuild_or_update)
            indexed_records = index.iter_files()
            files = [{
                "path": item.path, "sha256": item.sha256,
                "size_bytes": item.size_bytes, "line_count": item.line_count,
                "content": item._content,
            } for item in indexed_records]
            file_hashes = {item["path"]: item["sha256"] for item in files}
            changed_count = sum(
                1 for path, digest in file_hashes.items()
                if previous_hashes.get(path) != digest
            )
            unchanged_count = sum(
                1 for path, digest in file_hashes.items()
                if previous_hashes.get(path) == digest
            )
            removed_count = len(set(previous_hashes) - set(file_hashes))
            analysis = await run_in_threadpool(
                analyze_repository, files, max_chunks=_MAX_SEMANTIC_CHUNKS
            )
            symbols = [
                {**item, "sha256": file_hashes[item["path"]]}
                for item in analysis["symbols"]
            ]
            references = [
                {**item, "sha256": file_hashes[item["path"]]}
                for item in analysis["references"]
            ]
            imports = [
                {**item, "sha256": file_hashes[item["path"]]}
                for item in analysis["imports"]
            ]
            chunks = [
                {**item, "sha256": file_hashes[item["path"]]}
                for item in analysis["chunks"]
            ]
            try:
                existing_chunks = await store.get_active_chunks(
                    organization_id=organization_id, project_id=project_id,
                )
                reusable = {
                    (item.get("path"), item.get("chunk_index"), item.get("sha256"))
                    for item in existing_chunks
                    if isinstance(item.get("embedding"), list) and len(item["embedding"]) == 1536
                }
                chunks_requiring_embedding = [
                    item for item in chunks
                    if (item["path"], item["chunk_index"], item["sha256"]) not in reusable
                ]
                if chunks_requiring_embedding:
                    config = get_settings()
                    if config.openai_api_key is None or not config.openai_api_key.get_secret_value():
                        raise ModelConfigurationError("Embedding API key is not configured")
                    client = OpenAI(api_key=config.openai_api_key.get_secret_value())
                    try:
                        chunks = await _embed_new_chunks(chunks, existing_chunks, client=client)
                    finally:
                        client.close()
                else:
                    chunks = await _embed_new_chunks(
                        chunks, existing_chunks, client=None
                    )
                state = await store.publish(
                    organization_id=organization_id, project_id=project_id,
                    snapshot=snapshot, files=files, symbols=symbols,
                    references=references, imports=imports, chunks=chunks,
                    embedding_model=_EMBEDDING_MODEL, chunk_limit_reached=analysis["chunk_limit_reached"],
                    mongo_client=mongo_client, audit_store=audit_store, principal=principal,
                )
            except RepositoryIndexConflict as exc:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "REPOSITORY_INDEX_CONFLICT", "message": "The repository index changed concurrently; retry the refresh."},
                ) from exc
            return {
                "indexed": True,
                **state,
                "update": {
                    "changed": changed_count,
                    "unchanged": unchanged_count,
                    "removed": removed_count,
                    "skipped": update.skipped,
                    "total_bytes": update.total_bytes,
                },
            }
    except HTTPException:
        raise
    except (RepositoryIndexError, SnapshotError, ValueError) as exc:
        await _audit(
            request, principal, organization_id, project_id,
            "repository.index.refresh.failure", {"error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=422,
            detail={"code": "REPOSITORY_INDEX_REJECTED", "message": "The workspace snapshot could not be safely indexed."},
        ) from exc
    except PyMongoError as exc:
        await _audit(
            request, principal, organization_id, project_id,
            "repository.index.refresh.failure", {"error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=503,
            detail={"code": "REPOSITORY_STORE_UNAVAILABLE", "message": "Repository indexing storage is temporarily unavailable."},
        ) from exc
    except ModelConfigurationError as exc:
        await _audit(
            request, principal, organization_id, project_id,
            "repository.index.refresh.failure", {"error_type": "model_not_configured"},
        )
        raise HTTPException(
            status_code=503,
            detail={"code": "MODEL_NOT_CONFIGURED", "message": "The embedding provider is not configured."},
        ) from exc
    except Exception as exc:
        logger.warning("Repository index refresh failed (%s)", type(exc).__name__)
        await _audit(
            request, principal, organization_id, project_id,
            "repository.index.refresh.failure", {"error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=502,
            detail={"code": "REPOSITORY_INDEX_FAILED", "message": "Repository indexing is temporarily unavailable."},
        ) from exc


@router.get(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/repository-index/search",
    tags=["repository-intelligence"],
)
async def search_repository(
    request: Request,
    q: str = Query(min_length=1, max_length=512),
    case_sensitive: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
    organization_id: str = ApiPath(min_length=1, max_length=128),
    project_id: str = ApiPath(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    await _authorize(request, principal, organization_id, project_id)
    store = getattr(request.app.state, "repository_index_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={"code": "REPOSITORY_STORE_UNAVAILABLE"})
    try:
        state = await store.get_state(organization_id=organization_id, project_id=project_id)
        files = await store.get_active_files(organization_id=organization_id, project_id=project_id)
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "REPOSITORY_STORE_UNAVAILABLE"}) from exc
    if state is None:
        raise HTTPException(status_code=404, detail={"code": "REPOSITORY_INDEX_NOT_FOUND"})
    pattern = re.compile(re.escape(q), 0 if case_sensitive else re.IGNORECASE)
    hits = []
    for record in files:
        for line_number, line in enumerate(record["content"].splitlines(), start=1):
            if pattern.search(line):
                hits.append({
                    "path": record["path"], "line": line_number,
                    "snippet": line[:500], "sha256": record["sha256"],
                    "revision": state["revision"], "snapshot_id": state["snapshot_id"],
                })
                if len(hits) >= limit:
                    break
        if len(hits) >= limit:
            break
    await _audit(
        request, principal, organization_id, project_id,
        "repository.search.exact", {"query_length": len(q), "result_count": len(hits)},
    )
    return {"revision": state["revision"], "results": hits, "limit": limit}


@router.get(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/repository-index/symbols",
    tags=["repository-intelligence"],
)
async def search_repository_symbols(
    request: Request,
    name: str = Query(min_length=1, max_length=128),
    limit: int = Query(default=50, ge=1, le=100),
    organization_id: str = ApiPath(min_length=1, max_length=128),
    project_id: str = ApiPath(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    await _authorize(request, principal, organization_id, project_id)
    store = getattr(request.app.state, "repository_index_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={"code": "REPOSITORY_STORE_UNAVAILABLE"})
    try:
        results = await store.search_symbols(
            organization_id=organization_id, project_id=project_id, name=name, limit=limit,
        )
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "REPOSITORY_STORE_UNAVAILABLE"}) from exc
    await _audit(
        request, principal, organization_id, project_id,
        "repository.symbols.search", {"name_length": len(name), "result_count": len(results)},
    )
    return {"results": [
        {
            "name": item["name"], "qualified_name": item["qualified_name"],
            "kind": item["kind"], "path": item["path"], "line": item["line"],
            "sha256": item["sha256"], "revision": item["revision"],
            "snapshot_id": item["snapshot_id"],
        } for item in results
    ], "limit": limit}


@router.get(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/repository-index/references",
    tags=["repository-intelligence"],
)
async def search_repository_references(
    request: Request,
    name: str = Query(min_length=1, max_length=128),
    limit: int = Query(default=100, ge=1, le=200),
    organization_id: str = ApiPath(min_length=1, max_length=128),
    project_id: str = ApiPath(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    await _authorize(request, principal, organization_id, project_id)
    store = getattr(request.app.state, "repository_index_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={"code": "REPOSITORY_STORE_UNAVAILABLE"})
    try:
        results = await store.search_references(
            organization_id=organization_id, project_id=project_id, name=name, limit=limit,
        )
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "REPOSITORY_STORE_UNAVAILABLE"}) from exc
    await _audit(
        request, principal, organization_id, project_id,
        "repository.references.search", {"name_length": len(name), "result_count": len(results)},
    )
    return {"results": [
        {
            "name": item["name"], "path": item["path"], "line": item["line"],
            "sha256": item["sha256"], "revision": item["revision"],
            "snapshot_id": item["snapshot_id"],
        } for item in results
    ], "limit": limit}


@router.get(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/repository-index/dependency-graph",
    tags=["repository-intelligence"],
)
async def get_repository_dependency_graph(
    request: Request,
    organization_id: str = ApiPath(min_length=1, max_length=128),
    project_id: str = ApiPath(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    await _authorize(request, principal, organization_id, project_id)
    store = getattr(request.app.state, "repository_index_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={"code": "REPOSITORY_STORE_UNAVAILABLE"})
    try:
        graph = await store.dependency_graph(
            organization_id=organization_id, project_id=project_id,
        )
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "REPOSITORY_STORE_UNAVAILABLE"}) from exc
    await _audit(
        request, principal, organization_id, project_id,
        "repository.graph.read", {"node_count": len(graph["nodes"]), "edge_count": len(graph["edges"])},
    )
    return graph


@router.post(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/repository-index/semantic-search",
    tags=["repository-intelligence"],
)
async def semantic_repository_search(
    payload: SemanticSearchRequest,
    request: Request,
    organization_id: str = ApiPath(min_length=1, max_length=128),
    project_id: str = ApiPath(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    if payload.cloud_model_consent is not True:
        raise HTTPException(
            status_code=400,
            detail={"code": "CLOUD_MODEL_CONSENT_REQUIRED", "message": "Explicit consent is required before sending the search query to the embedding provider."},
        )
    await _authorize(request, principal, organization_id, project_id)
    store = getattr(request.app.state, "repository_index_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={"code": "REPOSITORY_STORE_UNAVAILABLE"})
    try:
        config = get_settings()
        if config.openai_api_key is None or not config.openai_api_key.get_secret_value():
            raise ModelConfigurationError("Embedding API key is not configured")
        client = OpenAI(api_key=config.openai_api_key.get_secret_value())
        try:
            vectors = await run_in_threadpool(
                _embedding_batch, client, [payload.query]
            )
        finally:
            client.close()
        state = await store.get_state(
            organization_id=organization_id, project_id=project_id,
        )
        if state is None:
            raise HTTPException(status_code=404, detail={"code": "REPOSITORY_INDEX_NOT_FOUND"})
        results = await store.search_semantic(
            organization_id=organization_id, project_id=project_id,
            query_embedding=vectors[0], limit=payload.limit,
        )
    except ModelConfigurationError as exc:
        raise HTTPException(status_code=503, detail={"code": "MODEL_NOT_CONFIGURED"}) from exc
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "REPOSITORY_STORE_UNAVAILABLE"}) from exc
    except Exception as exc:
        logger.warning("Semantic repository search failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail={"code": "SEMANTIC_SEARCH_UNAVAILABLE"}) from exc
    await _audit(
        request, principal, organization_id, project_id,
        "repository.search.semantic",
        {"query_length": len(payload.query), "result_count": len(results)},
    )
    return {"results": results, "limit": payload.limit, "embedding_model": _EMBEDDING_MODEL}
