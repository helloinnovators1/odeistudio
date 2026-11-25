from __future__ import annotations

from datetime import datetime, timezone

import pytest

from odei_api.services.execution_runs import (
    ExecutionRun,
    ExecutionRunStatus,
    validate_execution_request,
)


def make_run(**overrides):
    values = {"id": "run-1", "organization_id": "org-1", "project_id": "project-1",
        "task_id": "task-1", "requester_issuer": "https://identity.example",
        "requester_subject": "subject-1", "profile_id": "python-tests",
        "snapshot_sha256": "a" * 64, "arguments": ("-q",)}
    values.update(overrides)
    return ExecutionRun(**values)

def test_new_run_is_queued_and_hides_lease_token():
    run = make_run()
    assert run.status is ExecutionRunStatus.QUEUED
    assert run.version == 0 and run.attempts == 0
    assert "lease_token" not in repr(run)

@pytest.mark.parametrize("overrides", [
    {"profile_id": "../python"}, {"snapshot_sha256": "A" * 64},
    {"snapshot_sha256": "not-a-digest"}, {"arguments": "python -m pytest"},
    {"arguments": ("x\nmalicious",)}, {"arguments": ("x" * 1025,)},
    {"arguments": tuple(str(i) for i in range(33))},
    {"organization_id": "../other-tenant"}, {"requester_issuer": "http://identity.example"},
])
def test_new_run_rejects_invalid_or_untrusted_fields(overrides):
    with pytest.raises((ValueError, TypeError)):
        make_run(**overrides)

def test_argument_vector_is_not_shell_joined():
    args = validate_execution_request(profile_id="node-tests", snapshot_sha256="b" * 64,
        arguments=("--runInBand", "path with spaces/test.py"))
    assert args == ("--runInBand", "path with spaces/test.py")

def test_persisted_non_initial_state_can_be_hydrated():
    run = make_run(status=ExecutionRunStatus.LEASED, version=1, attempts=1,
                   worker_id="worker-1", lease_token="f" * 32)
    assert run.status is ExecutionRunStatus.LEASED
    assert run.version == 1
    assert run.attempts == 1
    assert "f" * 32 not in repr(run)



def test_bound_run_pins_repository_identity_and_exact_base():
    run = make_run(
        repository_binding_version=4, repository_id=123,
        repository_node_id="R_kgDOabc", repository_installation_id=77,
        repository_owner="Acme", repository_name="Service",
        repository_default_branch="main", repository_base_sha="b" * 40,
    )
    assert run.repository_binding_version == 4
    assert run.repository_base_sha == "b" * 40


def test_worker_provenance_requires_complete_exact_review_metadata():
    values = {
        "repository_binding_version": 4, "repository_id": 123,
        "repository_node_id": "R_kgDOabc", "repository_installation_id": 77,
        "repository_owner": "Acme", "repository_name": "Service",
        "repository_default_branch": "main", "repository_base_sha": "b" * 40,
        "worker_commit_sha": "c" * 40, "worker_tree_sha": "d" * 40,
        "worker_branch": "odei/nexus/run-1", "worker_pull_request_number": 12,
        "worker_pull_request_url": "https://github.com/Acme/Service/pull/12",
        "worker_provenance_at": datetime.now(timezone.utc),
    }
    run = make_run(**values)
    assert run.worker_commit_sha == "c" * 40
    assert run.worker_pull_request_number == 12
    with pytest.raises(ValueError):
        make_run(repository_binding_version=4)
    with pytest.raises(ValueError):
        make_run(**{**values, "worker_pull_request_url": "https://evil.example/pull/12"})


