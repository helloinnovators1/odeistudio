"""Server-configured platform operator RBAC for MAC.

Role assignments are deployment-owned and keyed by verified issuer+subject.
Client-supplied role claims and request parameters are never consulted.
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException

MAC_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "platform_owner": frozenset({
        "mac:read", "mac:identity:manage", "mac:environment:manage",
        "mac:secrets:manage", "mac:providers:manage", "mac:security:manage",
        "mac:deployments:request", "mac:deployments:approve", "mac:audit:read",
    }),
    "super_admin": frozenset({
        "mac:read", "mac:environment:manage", "mac:secrets:manage",
        "mac:providers:manage", "mac:security:manage",
        "mac:deployments:approve", "mac:audit:read",
    }),
    "infrastructure_admin": frozenset({
        "mac:read", "mac:environment:manage", "mac:providers:manage",
        "mac:deployments:request",
    }),
    "security_admin": frozenset({
        "mac:read", "mac:secrets:manage", "mac:security:manage", "mac:audit:read",
    }),
    "deployment_approver": frozenset({"mac:read", "mac:deployments:approve"}),
    "read_only_auditor": frozenset({"mac:read", "mac:audit:read"}),
}
_ALLOWED_ROLES = frozenset(MAC_ROLE_PERMISSIONS)
_AUDIT_SUBJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")


def parse_mac_operator_registry(raw: str) -> dict[tuple[str, str], tuple[str, ...]]:
    """Parse bounded deployment-owned issuer/subject role assignments."""
    if not isinstance(raw, str) or not raw.strip():
        return {}
    if len(raw) > 262_144:
        raise ValueError("MAC operator registry exceeds the size limit")
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("MAC_PLATFORM_OPERATORS_JSON must be valid JSON") from exc
    if not isinstance(values, list) or not 1 <= len(values) <= 500:
        raise ValueError("MAC operator registry must contain 1 to 500 assignments")

    assignments: dict[tuple[str, str], tuple[str, ...]] = {}
    for item in values:
        if not isinstance(item, dict) or set(item) != {"issuer", "subject", "roles"}:
            raise ValueError("Each MAC operator assignment requires issuer, subject and roles only")
        issuer = item["issuer"]
        subject = item["subject"]
        roles = item["roles"]
        if (
            not isinstance(issuer, str) or len(issuer) > 512
            or not issuer.startswith("https://")
        ):
            raise ValueError("MAC operator issuer must be an HTTPS issuer")
        try:
            parsed = urlsplit(issuer)
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("MAC operator issuer is invalid") from exc
        if (
            parsed.scheme != "https" or not parsed.netloc or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or issuer != issuer.strip()
        ):
            raise ValueError("MAC operator issuer is invalid")
        if (
            not isinstance(subject, str) or not _AUDIT_SUBJECT.fullmatch(subject)
        ):
            raise ValueError("MAC operator subject is invalid")
        if (
            not isinstance(roles, list) or not roles or len(roles) > len(_ALLOWED_ROLES)
            or any(not isinstance(role, str) or role not in _ALLOWED_ROLES for role in roles)
            or len(set(roles)) != len(roles)
        ):
            raise ValueError("MAC operator roles contain an unknown or duplicate role")
        key = (issuer, subject)
        if key in assignments:
            raise ValueError("MAC operator issuer/subject assignments must be unique")
        assignments[key] = tuple(sorted(roles))
    return assignments


def resolve_mac_access(raw: str, *, issuer: str, subject: str) -> dict[str, list[str]]:
    """Resolve roles and effective permissions for one verified principal."""
    assignments = parse_mac_operator_registry(raw)
    roles = assignments.get((issuer, subject), ())
    permissions: set[str] = set()
    for role in roles:
        permissions.update(MAC_ROLE_PERMISSIONS[role])
    return {"roles": list(roles), "permissions": sorted(permissions)}


def require_mac_permission(access: dict[str, Any], permission: str) -> None:
    """Fail closed unless the resolved server-side role grants the permission."""
    permissions = access.get("permissions", [])
    if permission not in permissions:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "MAC_PERMISSION_DENIED",
                "message": "The verified platform operator lacks the required MAC permission.",
            },
        )
