"""Load only deployment-owned, digest-pinned execution profiles."""
from __future__ import annotations

import json

from odei_api.config import Settings
from odei_api.services.execution_sandbox import SandboxProfile, SandboxProfileRegistry


def load_execution_profiles(settings: Settings) -> SandboxProfileRegistry | None:
    raw = settings.execution_profiles_json.strip()
    if not raw:
        return None
    try:
        values = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("EXECUTION_PROFILES_JSON must be valid JSON") from exc
    if not isinstance(values, list) or not 1 <= len(values) <= 20:
        raise ValueError("EXECUTION_PROFILES_JSON must contain 1 to 20 profiles")
    profiles = []
    allowed = {"name", "image", "command", "timeout_seconds", "memory_mb",
               "cpus", "pids_limit", "tmpfs_mb", "max_output_bytes"}
    for value in values:
        if not isinstance(value, dict) or set(value) - allowed:
            raise ValueError("Execution profile contains unknown fields")
        if not {"name", "image", "command"} <= set(value):
            raise ValueError("Execution profile requires name, image and command")
        command = value["command"]
        if not isinstance(command, list):
            raise ValueError("Execution profile command must be a JSON array")
        profiles.append(SandboxProfile(**{**value, "command": tuple(command)}))
    return SandboxProfileRegistry(profiles)
