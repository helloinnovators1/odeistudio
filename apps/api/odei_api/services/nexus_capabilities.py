"""Central server-side capability policy for NEXUS interaction modes."""
from __future__ import annotations

from typing import Final

MODES: Final[frozenset[str]] = frozenset({"ask", "plan", "agent", "debug"})

# Capabilities are intentionally narrow. New tools require an explicit grant.
_MODE_CAPABILITIES: Final[dict[str, frozenset[str]]] = {
    "ask": frozenset({"chat.read"}),
    "plan": frozenset({"task.plan"}),
    "agent": frozenset({"workspace.inspect", "workspace.read", "patch.propose"}),
    "debug": frozenset({"chat.debug"}),
}

class NexusCapabilityDenied(PermissionError):
    """The selected NEXUS mode does not grant the requested capability."""

class NexusCapabilityPolicy:
    """Fail-closed authorization for server-side NEXUS capabilities."""

    @staticmethod
    def allows(mode: str, capability: str) -> bool:
        return mode in MODES and capability in _MODE_CAPABILITIES.get(mode, frozenset())

    @classmethod
    def require(cls, mode: str, capability: str) -> None:
        if not cls.allows(mode, capability):
            raise NexusCapabilityDenied(f"Mode {mode!r} does not grant capability {capability!r}")

    @staticmethod
    def capabilities(mode: str) -> frozenset[str]:
        return _MODE_CAPABILITIES.get(mode, frozenset())
