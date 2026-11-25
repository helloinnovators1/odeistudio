"""FastAPI application entry point and dependency lifecycle."""
import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from hmac import compare_digest
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr
from pymongo.errors import PyMongoError
from starlette.concurrency import run_in_threadpool

from odei_api.config import get_settings, parse_cors_origins
from odei_api.model_client import ModelConfigurationError, get_openai_client
from odei_api.mongo_client import create_mongo_client
from odei_api.security.auth import (
    Principal,
    get_current_principal,
    require_organization_membership,
)
from odei_api.security.mac_rbac import resolve_mac_access
from odei_api.services.audit_store import MongoAuditEventStore
from odei_api.services.conversation_store import MongoConversationStore
from odei_api.services.execution_artifacts import MongoExecutionArtifactStore
from odei_api.services.execution_profiles import load_execution_profiles
from odei_api.services.execution_runs import MongoExecutionRunStore
from odei_api.services.github_app import GitHubAppInstallationClient
from odei_api.services.mac_deployments import MongoMacDeploymentStore
from odei_api.services.mac_environment_api import router as mac_environment_router
from odei_api.services.mac_revision_environment_store import MongoMacRevisionEnvironmentStore
from odei_api.services.mad_incidents import (
    MadIncidentConflict,
    MadIncidentNotFound,
    MadIncidentValidationError,
    MongoMadIncidentStore,
)
from odei_api.services.mad_telemetry import collect_mad_execution_metrics, evaluate_mad_alerts
from odei_api.services.nexus_conversations import router as nexus_conversations_router
from odei_api.services.nexus_execution import router as nexus_execution_router
from odei_api.services.nexus_inspection import router as nexus_inspection_router
from odei_api.services.nexus_patch_proposals import MongoPatchProposalStore
from odei_api.services.nexus_patch_proposals import router as nexus_patch_proposals_router
from odei_api.services.nexus_tasks import router as nexus_tasks_router
from odei_api.services.nexus_repository_bindings import router as nexus_repository_bindings_router
from odei_api.services.parallel_jobs import MongoParallelJobStore
from odei_api.services.parallel_jobs_api import router as parallel_jobs_router
from odei_api.services.planning import PlanningError, create_task_plan
from odei_api.services.projects import router as projects_router
from odei_api.services.repository_index_store import MongoRepositoryIndexStore
from odei_api.services.repository_intelligence import router as repository_intelligence_router
from odei_api.services.task_store import MongoTaskStore
from odei_api.services.workspace_snapshot_store import MongoWorkspaceSnapshotStore

logger = logging.getLogger(__name__)


class MadIncidentTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["acknowledge", "assign", "resolve", "reopen"]
    expected_version: int = Field(ge=1)
    assignee: StrictStr | None = Field(default=None, min_length=1, max_length=128)

settings = get_settings()
auth_principal_dependency = Depends(get_current_principal)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Own the optional MongoDB client for the lifetime of the API process."""
    client = None
    database_name = None
    http_client = httpx.AsyncClient(timeout=5.0)
    application.state.http_client = http_client
    application.state.github_app_client = GitHubAppInstallationClient(
        app_id=settings.github_app_id,
        private_key_b64=settings.github_app_private_key_b64,
        http_client=http_client,
    )
    application.state.jwks_cache = None
    application.state.jwks_lock = asyncio.Lock()
    application.state.execution_profile_registry = load_execution_profiles(settings)
    try:
        if settings.mongodb_uri is not None and settings.mongodb_uri.get_secret_value():
            client, database_name = create_mongo_client(settings)
        application.state.mongo_client = client
        application.state.mongo_database = client[database_name] if client and database_name else None
        application.state.audit_event_store = None
        application.state.mac_environment_store = None
        application.state.mac_deployment_store = None
        application.state.mad_incident_store = None
        if application.state.mongo_database is not None:
            audit_store = MongoAuditEventStore(application.state.mongo_database["audit_events"])
            await audit_store.initialize()
            application.state.audit_event_store = audit_store
            mac_environment_store = MongoMacRevisionEnvironmentStore(
                application.state.mongo_database["mac_environments"],
                application.state.mongo_database["mac_environment_revisions"],
            )
            await mac_environment_store.initialize()
            application.state.mac_environment_store = mac_environment_store
            mac_deployment_store = MongoMacDeploymentStore(
                application.state.mongo_database["mac_deployment_attempts"],
                mac_environment_store,
            )
            await mac_deployment_store.initialize()
            application.state.mac_deployment_store = mac_deployment_store
            incident_store = MongoMadIncidentStore(application.state.mongo_database["mad_incidents"])
            await incident_store.initialize()
            application.state.mad_incident_store = incident_store
            await application.state.mongo_database["projects"].create_index(
                [("organization_id", 1), ("project_id", 1)], unique=True
            )
            await application.state.mongo_database["projects"].create_index(
                [("organization_id", 1), ("status", 1), ("created_at", -1)]
            )
            await application.state.mongo_database["project_memberships"].create_index(
                [("organization_id", 1), ("project_id", 1),
                 ("identity_issuer", 1), ("identity_subject", 1)], unique=True
            )
            await application.state.mongo_database["project_memberships"].create_index(
                [("organization_id", 1), ("identity_issuer", 1),
                 ("identity_subject", 1), ("status", 1)]
            )
            task_store = MongoTaskStore(
                application.state.mongo_database["tasks"],
                application.state.mongo_database["task_events"],
                client,
                audit_store=audit_store,
            )
            await task_store.initialize()
            application.state.task_store = task_store
            conversation_store = MongoConversationStore(application.state.mongo_database["nexus_conversations"])
            await conversation_store.initialize()
            application.state.conversation_store = conversation_store
            patch_proposal_store = MongoPatchProposalStore(application.state.mongo_database["nexus_patch_proposals"])
            await patch_proposal_store.initialize()
            application.state.patch_proposal_store = patch_proposal_store
            execution_run_store = MongoExecutionRunStore(
                application.state.mongo_database["execution_runs"],
                application.state.mongo_database["execution_run_events"],
                client,
                audit_store=audit_store,
            )
            await execution_run_store.initialize()
            application.state.execution_run_store = execution_run_store
            parallel_job_store = MongoParallelJobStore(
                application.state.mongo_database["nexus_parallel_jobs"],
                application.state.mongo_database["nexus_parallel_job_groups"],
                application.state.mongo_database["nexus_parallel_job_events"],
            )
            await parallel_job_store.initialize()
            application.state.parallel_job_store = parallel_job_store
            snapshot_store = MongoWorkspaceSnapshotStore(application.state.mongo_database)
            await snapshot_store.initialize()
            application.state.workspace_snapshot_store = snapshot_store
            repository_index_store = MongoRepositoryIndexStore(application.state.mongo_database)
            await repository_index_store.initialize()
            application.state.repository_index_store = repository_index_store
            await application.state.mongo_database["nexus_repository_bindings"].create_index(
                [("organization_id", 1), ("project_id", 1)], unique=True,
            )
            artifact_store = MongoExecutionArtifactStore(application.state.mongo_database)
            await artifact_store.initialize()
            application.state.execution_artifact_store = artifact_store
        else:
            application.state.mac_environment_store = None
            application.state.mac_deployment_store = None
            application.state.task_store = None
            application.state.conversation_store = None
            application.state.patch_proposal_store = None
            application.state.execution_run_store = None
            application.state.parallel_job_store = None
            application.state.workspace_snapshot_store = None
            application.state.repository_index_store = None
            application.state.execution_artifact_store = None
        yield
    finally:
        if client is not None:
            await client.close()
        await http_client.aclose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API foundation for ODEI Studio and ODEI NEXUS.",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
    lifespan=lifespan,
)
app.include_router(nexus_tasks_router)
app.include_router(parallel_jobs_router)
app.include_router(nexus_execution_router)
app.include_router(nexus_conversations_router)
app.include_router(nexus_inspection_router)
app.include_router(nexus_patch_proposals_router)
app.include_router(repository_intelligence_router)
app.include_router(nexus_repository_bindings_router)
app.include_router(projects_router)
app.include_router(mac_environment_router)

# Keep origins empty until the deployment's exact web origins are configured.
# Wildcard CORS with credentials is deliberately not enabled.
app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_cors_origins(settings.cors_allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {"service": "odei-studio-api", "status": "running"}


@app.get(f"{settings.api_prefix}/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    """Process liveness only; does not claim database/provider readiness."""
    return {"status": "alive"}


@app.get(f"{settings.api_prefix}/health/ready", tags=["health"])
async def readiness(request: Request) -> dict[str, object]:
    """Require live MongoDB plus replica-set/sharded transaction capability."""
    client = getattr(request.app.state, "mongo_client", None)
    if client is None:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": {"mongodb": "not_configured"}},
        )
    try:
        await client.admin.command("ping")
        topology = await client.admin.command("hello")
    except Exception as exc:
        logger.warning("MongoDB readiness check failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": {"mongodb": "unavailable"}},
        ) from exc
    if not isinstance(topology, dict) or not (
        topology.get("setName") or topology.get("msg") == "isdbgrid"
    ):
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "checks": {"mongodb": "ok", "transactions": "unsupported"},
            },
        )
    return {"status": "ready", "checks": {"mongodb": "ok", "transactions": "supported"}}


@app.get(
    f"{settings.api_prefix}/internal/mad/execution-metrics",
    tags=["internal-operations"],
    include_in_schema=False,
)
async def mad_execution_metrics(
    request: Request,
    supplied_token: str | None = Header(default=None, alias="X-ODEI-MAD-Token"),
) -> dict[str, object]:
    """Internal platform metrics endpoint; protect additionally with network policy."""
    configured_token = settings.mad_metrics_token
    if configured_token is None or not configured_token.get_secret_value():
        raise HTTPException(
            status_code=503,
            detail={"code": "MAD_METRICS_NOT_CONFIGURED", "message": "MAD metrics are not configured."},
        )
    if supplied_token is None or not compare_digest(
        supplied_token.encode("utf-8"), configured_token.get_secret_value().encode("utf-8")
    ):
        raise HTTPException(
            status_code=401,
            detail={"code": "MAD_METRICS_UNAUTHORIZED", "message": "A valid operations credential is required."},
        )
    database = getattr(request.app.state, "mongo_database", None)
    if database is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "MAD_METRICS_UNAVAILABLE", "message": "Operational metrics storage is unavailable."},
        )
    try:
        metrics = await collect_mad_execution_metrics(database)
        metrics["alerts"] = evaluate_mad_alerts(metrics)
        return metrics
    except PyMongoError as exc:
        logger.warning("MAD metrics collection failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={"code": "MAD_METRICS_UNAVAILABLE", "message": "Operational metrics are temporarily unavailable."},
        ) from exc


@app.get(f"{settings.api_prefix}/mad/execution-metrics", tags=["mad"])
async def mad_operator_execution_metrics(
    request: Request,
    principal: Principal = auth_principal_dependency,
) -> dict[str, object]:
    """Read aggregate MAD metrics using a verified, explicitly granted operator scope."""
    audit_store = getattr(request.app.state, "audit_event_store", None)
    if audit_store is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Operator audit storage is unavailable."},
        )

    async def append_access_audit(outcome: str) -> None:
        try:
            await audit_store.append(
                organization_id="platform",
                actor_issuer=principal.issuer,
                actor_subject=principal.subject,
                action="mad.metrics.read",
                target_type="platform_metrics",
                target_id="execution",
                outcome=outcome,
                request_id=uuid4().hex,
                metadata={"authorization_scope": "mad:read"},
            )
        except Exception as exc:
            logger.error("MAD operator access audit failed (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=503,
                detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Operator audit could not be recorded."},
            ) from exc

    if "mad:read" not in principal.scopes:
        await append_access_audit("denied")
        raise HTTPException(
            status_code=403,
            detail={"code": "MAD_SCOPE_REQUIRED", "message": "The verified identity lacks the mad:read scope."},
        )

    database = getattr(request.app.state, "mongo_database", None)
    if database is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "MAD_METRICS_UNAVAILABLE", "message": "Operational metrics storage is unavailable."},
        )
    try:
        metrics = await collect_mad_execution_metrics(database)
    except PyMongoError as exc:
        logger.warning("MAD operator metrics collection failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={"code": "MAD_METRICS_UNAVAILABLE", "message": "Operational metrics are temporarily unavailable."},
        ) from exc
    metrics["alerts"] = evaluate_mad_alerts(metrics)
    incident_store = getattr(request.app.state, "mad_incident_store", None)
    mongo_client = getattr(request.app.state, "mongo_client", None)
    if incident_store is None or mongo_client is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "MAD_INCIDENTS_UNAVAILABLE", "message": "Transactional incident and audit storage is unavailable."},
        )
    try:
        await _record_mad_alerts_with_audit(
            mongo_client=mongo_client,
            incident_store=incident_store,
            audit_store=audit_store,
            alerts=metrics["alerts"],
            principal=principal,
        )
    except Exception as exc:
        logger.warning("MAD alert observation transaction failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={"code": "MAD_INCIDENTS_UNAVAILABLE", "message": "Alert observations and their audit could not be committed."},
        ) from exc
    return metrics


@app.get(f"{settings.api_prefix}/mad/incidents", tags=["mad"])
async def mad_list_incidents(
    request: Request,
    include_resolved: bool = False,
    limit: int = 100,
    principal: Principal = auth_principal_dependency,
) -> dict[str, object]:
    audit_store = getattr(request.app.state, "audit_event_store", None)
    incident_store = getattr(request.app.state, "mad_incident_store", None)
    if audit_store is None or incident_store is None:
        raise HTTPException(status_code=503, detail={"code": "MAD_INCIDENTS_UNAVAILABLE", "message": "Incident and audit storage is unavailable."})
    allowed = "mad:read" in principal.scopes
    try:
        await audit_store.append(
            organization_id="platform", actor_issuer=principal.issuer,
            actor_subject=principal.subject, action="mad.incidents.read",
            target_type="platform_incidents", target_id="execution",
            outcome="success" if allowed else "denied", request_id=uuid4().hex,
            metadata={"include_resolved": include_resolved, "limit": limit},
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Incident access audit could not be recorded."}) from exc
    if not allowed:
        raise HTTPException(status_code=403, detail={"code": "MAD_SCOPE_REQUIRED", "message": "The verified identity lacks the mad:read scope."})
    try:
        incidents = await incident_store.list_incidents(include_resolved=include_resolved, limit=limit)
    except MadIncidentValidationError as exc:
        raise HTTPException(status_code=422, detail={"code": "MAD_INCIDENT_QUERY_INVALID", "message": str(exc)}) from exc
    for incident in incidents:
        incident["id"] = incident.pop("_id", incident.get("incident_id"))
    return {"incidents": incidents}


async def _record_mad_alerts_with_audit(
    *,
    mongo_client,
    incident_store: MongoMadIncidentStore,
    audit_store: MongoAuditEventStore,
    alerts: list[dict[str, object]],
    principal: Principal,
) -> None:
    """Commit alert-observation changes and their success audit atomically."""
    async with mongo_client.start_session() as session:
        async def transaction(active_session):
            await incident_store.record_alerts(alerts, session=active_session)
            await audit_store.append(
                organization_id="platform",
                actor_issuer=principal.issuer,
                actor_subject=principal.subject,
                action="mad.metrics.read",
                target_type="platform_metrics",
                target_id="execution",
                outcome="success",
                request_id=uuid4().hex,
                metadata={"required_scope": "mad:read", "alert_count": len(alerts)},
                session=active_session,
            )

        await session.with_transaction(transaction)


async def _transition_mad_incident_with_audit(
    *,
    mongo_client,
    incident_store: MongoMadIncidentStore,
    audit_store: MongoAuditEventStore,
    incident_id: str,
    action: str,
    assignee: str | None,
    expected_version: int,
    principal: Principal,
) -> dict[str, object]:
    """Commit the incident CAS and its success audit in one Mongo transaction."""
    async with mongo_client.start_session() as session:
        async def transaction(active_session):
            incident = await incident_store.transition(
                incident_id=incident_id,
                action=action,
                actor=principal.subject,
                expected_version=expected_version,
                assignee=assignee,
                session=active_session,
            )
            await audit_store.append(
                organization_id="platform",
                actor_issuer=principal.issuer,
                actor_subject=principal.subject,
                action="mad.incident." + action,
                target_type="platform_incident",
                target_id=incident_id,
                outcome="success",
                request_id=uuid4().hex,
                metadata={"version": incident["version"], "status": incident["status"]},
                session=active_session,
            )
            return incident

        return await session.with_transaction(transaction)


@app.post(settings.api_prefix + "/mad/incidents/{incident_id}/transitions", tags=["mad"])
async def mad_transition_incident(
    incident_id: str,
    payload: MadIncidentTransitionRequest,
    request: Request,
    principal: Principal = auth_principal_dependency,
) -> dict[str, object]:
    audit_store = getattr(request.app.state, "audit_event_store", None)
    incident_store = getattr(request.app.state, "mad_incident_store", None)
    mongo_client = getattr(request.app.state, "mongo_client", None)
    if audit_store is None or incident_store is None or mongo_client is None:
        raise HTTPException(status_code=503, detail={"code": "MAD_INCIDENTS_UNAVAILABLE", "message": "Transactional incident and audit storage is unavailable."})
    allowed = "mad:incident:manage" in principal.scopes
    if not allowed:
        try:
            await audit_store.append(
                organization_id="platform", actor_issuer=principal.issuer,
                actor_subject=principal.subject, action="mad.incident.transition",
                target_type="platform_incident", target_id=incident_id,
                outcome="denied", request_id=uuid4().hex,
                metadata={"transition": payload.action},
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Incident denial audit could not be recorded."}) from exc
        raise HTTPException(status_code=403, detail={"code": "MAD_INCIDENT_SCOPE_REQUIRED", "message": "The verified identity lacks mad:incident:manage."})
    try:
        incident = await _transition_mad_incident_with_audit(
            mongo_client=mongo_client,
            incident_store=incident_store,
            audit_store=audit_store,
            incident_id=incident_id,
            action=payload.action,
            assignee=payload.assignee,
            expected_version=payload.expected_version,
            principal=principal,
        )
    except MadIncidentNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "MAD_INCIDENT_NOT_FOUND", "message": "Incident does not exist."}) from exc
    except MadIncidentConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "MAD_INCIDENT_CONFLICT", "message": str(exc)}) from exc
    except MadIncidentValidationError as exc:
        raise HTTPException(status_code=422, detail={"code": "MAD_INCIDENT_TRANSITION_INVALID", "message": str(exc)}) from exc
    except Exception as exc:
        logger.error("MAD incident transaction failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail={"code": "MAD_INCIDENT_TRANSACTION_FAILED", "message": "The incident transition and audit could not be committed. Refresh the incident before retrying."}) from exc
    incident["id"] = incident.pop("_id", incident.get("incident_id"))
    return {"incident": incident}


@app.get(f"{settings.api_prefix}/mac/access", tags=["mac"])
async def mac_operator_access(
    request: Request,
    principal: Principal = auth_principal_dependency,
) -> dict[str, list[str]]:
    """Resolve MAC roles from deployment-owned assignments, never token-supplied roles."""
    registry = settings.mac_platform_operators_json
    if not registry.strip():
        raise HTTPException(
            status_code=503,
            detail={"code": "MAC_OPERATOR_REGISTRY_NOT_CONFIGURED",
                    "message": "Platform operator assignments are not configured."},
        )
    try:
        access = resolve_mac_access(
            registry, issuer=principal.issuer, subject=principal.subject,
        )
    except ValueError as exc:
        logger.error("MAC operator registry validation failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={"code": "MAC_OPERATOR_REGISTRY_INVALID",
                    "message": "Platform operator assignments are unavailable."},
        ) from exc

    audit_store = getattr(request.app.state, "audit_event_store", None)
    if audit_store is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "AUDIT_STORE_UNAVAILABLE",
                    "message": "Platform authorization audit storage is unavailable."},
        )

    async def append_access_audit(outcome: str) -> None:
        try:
            await audit_store.append(
                organization_id="platform",
                actor_issuer=principal.issuer,
                actor_subject=principal.subject,
                action="mac.access.read",
                target_type="platform_access",
                target_id="mac",
                outcome=outcome,
                request_id=uuid4().hex,
                metadata={"roles": access["roles"]},
            )
        except Exception as exc:
            logger.error("MAC access audit append failed (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=503,
                detail={"code": "AUDIT_STORE_UNAVAILABLE",
                        "message": "Platform authorization audit could not be recorded."},
            ) from exc

    if not access["roles"]:
        await append_access_audit("denied")
        raise HTTPException(
            status_code=403,
            detail={"code": "MAC_OPERATOR_REQUIRED",
                    "message": "No platform operator role is assigned to this identity."},
        )
    await append_access_audit("success")
    return access


@app.get(f"{settings.api_prefix}/auth/me", tags=["auth"])
async def current_identity(principal: Principal = auth_principal_dependency) -> dict[str, str]:
    """Return only the verified caller identity; no client-supplied roles or tenant claims."""
    return {"subject": principal.subject, "issuer": principal.issuer}


async def _append_membership_audit(
    request: Request,
    *,
    principal: Principal,
    organization_id: str,
    outcome: str,
    reason: str | None = None,
) -> None:
    """Persist membership decisions before returning them; fail closed on audit errors."""
    store = getattr(request.app.state, "audit_event_store", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "AUDIT_STORE_UNAVAILABLE",
                "message": "Authorization audit storage is not available.",
            },
        )
    try:
        await store.append(
            organization_id=organization_id,
            actor_issuer=principal.issuer,
            actor_subject=principal.subject,
            action="organization.membership.read",
            target_type="organization",
            target_id=organization_id,
            outcome=outcome,
            request_id=uuid4().hex,
            metadata={"reason": reason} if reason else {},
        )
    except Exception as exc:
        logger.error("Membership authorization audit append failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "AUDIT_STORE_UNAVAILABLE",
                "message": "Authorization audit storage is temporarily unavailable.",
            },
        ) from exc



class NexusPlanRequest(BaseModel):
    """Bounded request for a plan; context is user-supplied and treated as untrusted."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task: str = Field(min_length=1, max_length=8_000)
    project_context: str = Field(default="", max_length=24_000)
    cloud_model_consent: StrictBool


async def _append_nexus_plan_audit(
    request: Request,
    *,
    principal: Principal,
    organization_id: str,
    plan_id: str,
    outcome: str,
    model: str | None = None,
) -> None:
    """Record plan outcomes without storing task text, repository context or plan content."""
    store = getattr(request.app.state, "audit_event_store", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Audit storage is not available."},
        )
    metadata = {"model": model} if model else {}
    try:
        await store.append(
            organization_id=organization_id,
            actor_issuer=principal.issuer,
            actor_subject=principal.subject,
            action="nexus.plan.create",
            target_type="nexus_plan",
            target_id=plan_id,
            outcome=outcome,
            request_id=uuid4().hex,
            metadata=metadata,
        )
    except Exception as exc:
        logger.error("NEXUS plan audit append failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Audit storage is temporarily unavailable."},
        ) from exc


@app.post(
    f"{settings.api_prefix}/organizations/{{organization_id}}/nexus/plan",
    tags=["nexus"],
)
async def create_nexus_plan(
    payload: NexusPlanRequest,
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    principal: Principal = auth_principal_dependency,
) -> dict[str, str]:
    """Create a plan for an active organization member after explicit cloud-model consent.

    This endpoint does not read local files, execute tools, write project files or
    authorize implementation. Repository context is caller-supplied, bounded and
    treated as untrusted input.
    """
    if organization_id != organization_id.strip():
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_ORGANIZATION_ID", "message": "Organization ID is invalid."},
        )
    if payload.cloud_model_consent is not True:
        raise HTTPException(
            status_code=400,
            detail={"code": "CLOUD_MODEL_CONSENT_REQUIRED", "message": "Explicit consent is required before sending task data to the cloud model."},
        )
    database = getattr(request.app.state, "mongo_database", None)
    if database is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "MEMBERSHIP_STORE_UNAVAILABLE", "message": "Organization membership storage is not configured."},
        )
    try:
        await require_organization_membership(
            database["organization_memberships"],
            principal=principal,
            organization_id=organization_id,
        )
    except HTTPException as exc:
        if exc.status_code == 403:
            await _append_membership_audit(
                request,
                principal=principal,
                organization_id=organization_id,
                outcome="denied",
                reason="active_membership_required",
            )
        raise
    except PyMongoError as exc:
        logger.warning("NEXUS organization membership lookup failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={"code": "MEMBERSHIP_STORE_UNAVAILABLE", "message": "Organization membership storage is temporarily unavailable."},
        ) from exc

    plan_id = uuid4().hex
    try:
        client, model = get_openai_client()
        plan = await run_in_threadpool(
            create_task_plan,
            client,
            model=model,
            task=payload.task,
            project_context=payload.project_context,
            cloud_model_consent=True,
        )
    except ModelConfigurationError as exc:
        await _append_nexus_plan_audit(
            request, principal=principal, organization_id=organization_id,
            plan_id=plan_id, outcome="failure",
        )
        raise HTTPException(
            status_code=503,
            detail={"code": "MODEL_NOT_CONFIGURED", "message": "The NEXUS model provider is not configured."},
        ) from exc
    except (PlanningError, ValueError) as exc:
        await _append_nexus_plan_audit(
            request, principal=principal, organization_id=organization_id,
            plan_id=plan_id, outcome="failure",
        )
        raise HTTPException(
            status_code=502,
            detail={"code": "NEXUS_PLANNING_FAILED", "message": "NEXUS could not produce a usable plan."},
        ) from exc
    except Exception as exc:
        logger.warning("NEXUS planning provider failed: %s", type(exc).__name__)
        await _append_nexus_plan_audit(
            request, principal=principal, organization_id=organization_id,
            plan_id=plan_id, outcome="failure",
        )
        raise HTTPException(
            status_code=502,
            detail={"code": "NEXUS_PROVIDER_UNAVAILABLE", "message": "The NEXUS planning provider is temporarily unavailable."},
        ) from exc

    await _append_nexus_plan_audit(
        request,
        principal=principal,
        organization_id=organization_id,
        plan_id=plan_id,
        outcome="success",
        model=plan.model,
    )
    return {"plan_id": plan_id, "organization_id": organization_id, "model": plan.model, "plan": plan.text}


@app.get(f"{settings.api_prefix}/organizations/{{organization_id}}/membership", tags=["organizations"])
async def current_organization_membership(
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    principal: Principal = auth_principal_dependency,
) -> dict[str, str]:
    """Return the caller's active membership, resolved only from trusted server-side storage."""
    if organization_id != organization_id.strip():
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_ORGANIZATION_ID", "message": "Organization ID is invalid."},
        )
    database = getattr(request.app.state, "mongo_database", None)
    if database is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "MEMBERSHIP_STORE_UNAVAILABLE",
                "message": "Organization membership storage is not configured.",
            },
        )
    try:
        membership = await require_organization_membership(
            database["organization_memberships"],
            principal=principal,
            organization_id=organization_id,
        )
    except HTTPException as exc:
        if exc.status_code == 403:
            await _append_membership_audit(
                request,
                principal=principal,
                organization_id=organization_id,
                outcome="denied",
                reason="active_membership_required",
            )
        raise
    except PyMongoError as exc:
        logger.warning("Organization membership lookup failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "MEMBERSHIP_STORE_UNAVAILABLE",
                "message": "Organization membership storage is temporarily unavailable.",
            },
        ) from exc

    role = membership.get("role") if isinstance(membership, dict) else None
    if not isinstance(role, str) or not role.strip():
        await _append_membership_audit(
            request,
            principal=principal,
            organization_id=organization_id,
            outcome="failure",
            reason="membership_record_invalid",
        )
        logger.error("Organization membership record has no valid role")
        raise HTTPException(
            status_code=503,
            detail={
                "code": "MEMBERSHIP_RECORD_INVALID",
                "message": "Organization membership data is not valid.",
            },
        )
    await _append_membership_audit(
        request,
        principal=principal,
        organization_id=organization_id,
        outcome="success",
    )
    return {"organization_id": organization_id, "role": role}
