"""Deterministic, bounded diagnostics for NEXUS execution artifacts."""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from odei_api.services.secret_redaction import redact_secrets

_MAX_EVIDENCE_LINES = 8
_MAX_EVIDENCE_CHARS = 240
_SIGNAL_PATTERNS = (
    ("MODULE_NOT_FOUND", re.compile(r"ModuleNotFoundError|No module named", re.IGNORECASE)),
    ("IMPORT_ERROR", re.compile(r"ImportError|cannot import name", re.IGNORECASE)),
    ("SYNTAX_ERROR", re.compile(r"SyntaxError|IndentationError", re.IGNORECASE)),
    ("ASSERTION_FAILURE", re.compile(r"AssertionError|assertion failed", re.IGNORECASE)),
    ("TEST_FAILURE", re.compile(r"FAILED\s|\bfailed\b|\bFAIL\b", re.IGNORECASE)),
    ("TRACEBACK", re.compile(r"Traceback \(most recent call last\)", re.IGNORECASE)),
    ("TIMEOUT", re.compile(r"timed? out|deadline exceeded", re.IGNORECASE)),
)


def build_execution_diagnostics(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Classify a stored execution result without invoking a model or echoing full logs."""
    if not isinstance(artifact, Mapping):
        raise TypeError("execution artifact must be a mapping")
    exit_code = artifact.get("exit_code")
    duration_ms = artifact.get("duration_ms")
    timed_out = artifact.get("timed_out")
    stdout = artifact.get("stdout", "")
    stderr = artifact.get("stderr", "")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise ValueError("execution exit code is invalid")
    if isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or duration_ms < 0:
        raise ValueError("execution duration is invalid")
    if not isinstance(timed_out, bool) or not isinstance(stdout, str) or not isinstance(stderr, str):
        raise ValueError("execution artifact fields are invalid")

    if timed_out:
        category = "timed_out"
        summary = "Execution exceeded its configured time limit."
    elif exit_code != 0:
        category = "failed"
        summary = f"Execution exited with status {exit_code}."
    else:
        category = "succeeded"
        summary = "Execution completed successfully."

    signals: list[str] = []
    evidence: list[str] = []
    for line in (stderr + "\n" + stdout).splitlines():
        matched = [name for name, pattern in _SIGNAL_PATTERNS if pattern.search(line)]
        for name in matched:
            if name not in signals:
                signals.append(name)
        if matched and len(evidence) < _MAX_EVIDENCE_LINES:
            safe = redact_secrets(line).strip()
            if safe:
                evidence.append(safe[:_MAX_EVIDENCE_CHARS])
    if timed_out and "TIMEOUT" not in signals:
        signals.insert(0, "TIMEOUT")

    if category == "timed_out":
        next_step = "Review the approved execution profile's time limit and the slowest reported operation."
    elif category == "failed":
        next_step = "Review the bounded evidence and the full authorized execution artifacts before proposing a repair."
    else:
        next_step = "No repair is indicated by this execution result."

    return {
        "category": category,
        "summary": summary,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "timed_out": timed_out,
        "signals": signals[:8],
        "evidence": evidence,
        "next_step": next_step,
    }
