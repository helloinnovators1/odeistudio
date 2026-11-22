"""Platform-admin-only MAD operational telemetry and alert routes."""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from odei_api.security import Principal, get_current_principal

router = APIRouter(prefix="/api/v1/admin/mad", tags=["mad"])


async def _require_platform_admin(request: Request, principal: Principal) -> dict:
    database = getattr(request.app.state, "mongo_database", None)
    if database is None:
        raise HTTPException(status_code=503, detail="Platform administration is unavailable.")
    admin = await database["platform_admins"].find_one({
        "issuer": principal.issuer,
        "subject": principal.subject,
        "status": "active",
        "roles": {"$in": ["platform_admin", "operations_admin", "security_admin"]},
    })
    if admin is None:
        raise HTTPException(status_code=403, detail="Platform administrator access is required.")
    return admin


async def _audit_admin_action(
    request: Request, principal: Principal, action: str, target_type: str, target_id: str,
) -> None:
    audit = getattr(request.app.state, "audit_event_store", None)
    if audit is None:
        raise HTTPException(status_code=503, detail="Audit storage is unavailable.")
    await audit.append(
        organization_id="platform",
        actor_issuer=principal.issuer,
        actor_subject=principal.subject,
        action=action,
        target_type=target_type,
        target_id=target_id,
        outcome="success",
        request_id=uuid4().hex,
        metadata={"surface": "mad"},
    )


@router.get("/overview")
async def get_mad_overview(
    request: Request,
    principal: Principal = Depends(get_current_principal),
):
    await _require_platform_admin(request, principal)
    telemetry = getattr(request.app.state, "mad_telemetry", None)
    if telemetry is None:
        raise HTTPException(status_code=503, detail="MAD telemetry is unavailable.")
    overview = await telemetry.overview()
    await _audit_admin_action(request, principal, "mad.overview.read", "mad_dashboard", "overview")
    return overview


@router.get("/alerts")
async def list_mad_alerts(
    request: Request,
    status: str | None = Query(default=None, pattern="^(open|acknowledged|resolved)$"),
    limit: int = Query(default=100, ge=1, le=200),
    principal: Principal = Depends(get_current_principal),
):
    await _require_platform_admin(request, principal)
    telemetry = getattr(request.app.state, "mad_telemetry", None)
    if telemetry is None:
        raise HTTPException(status_code=503, detail="MAD telemetry is unavailable.")
    alerts = await telemetry.list_alerts(status=status, limit=limit)
    await _audit_admin_action(request, principal, "mad.alerts.read", "mad_alert_collection", status or "all")
    return {"alerts": alerts}


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_mad_alert(
    alert_id: str,
    request: Request,
    principal: Principal = Depends(get_current_principal),
):
    await _require_platform_admin(request, principal)
    telemetry = getattr(request.app.state, "mad_telemetry", None)
    if telemetry is None:
        raise HTTPException(status_code=503, detail="MAD telemetry is unavailable.")
    alert = await telemetry.update_alert(
        alert_id=alert_id, action="acknowledge",
        actor_issuer=principal.issuer, actor_subject=principal.subject,
    )
    if alert is None:
        raise HTTPException(status_code=404, detail="Open MAD alert was not found.")
    await _audit_admin_action(request, principal, "mad.alert.acknowledge", "mad_alert", alert_id)
    return alert


@router.post("/alerts/{alert_id}/resolve")
async def resolve_mad_alert(
    alert_id: str,
    request: Request,
    principal: Principal = Depends(get_current_principal),
):
    await _require_platform_admin(request, principal)
    telemetry = getattr(request.app.state, "mad_telemetry", None)
    if telemetry is None:
        raise HTTPException(status_code=503, detail="MAD telemetry is unavailable.")
    alert = await telemetry.update_alert(
        alert_id=alert_id, action="resolve",
        actor_issuer=principal.issuer, actor_subject=principal.subject,
    )
    if alert is None:
        raise HTTPException(status_code=404, detail="Open MAD alert was not found.")
    await _audit_admin_action(request, principal, "mad.alert.resolve", "mad_alert", alert_id)
    return alert
