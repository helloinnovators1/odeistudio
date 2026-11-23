# NEXUS Task Planning and Approval

## Purpose

NEXUS task planning turns a user-authored goal into a bounded, durable implementation plan scoped to one organization and project. It is separate from ordinary chat and requires explicit cloud-model consent.

## Current API

- `POST /api/v1/organizations/{organization_id}/projects/{project_id}/tasks` creates a plan.
- `GET /api/v1/organizations/{organization_id}/projects/{project_id}/tasks/{task_id}` retrieves an authorized task.
- `POST .../tasks/{task_id}/approve` records project-owner approval using an expected version.
- `POST .../tasks/{task_id}/cancel` cancels a task using an expected version.
- Task lifecycle events are available through the task events endpoint with version-based pagination.

Every request authenticates the identity, verifies active organization membership, verifies project access, and applies task ownership rules. Task creation and state transitions are persisted with audit events through the task store's transactional boundary.

## Studio workflow

1. Select an authorized organization and project.
2. Enter a task goal in the NEXUS composer.
3. Explicitly check the cloud-model consent control.
4. Optionally attach the active file excerpt; it is not sent unless explicitly selected.
5. Choose **Plan task**.
6. Review the returned plan, status, task ID and version.
7. The project owner may approve or cancel the plan. The API rejects approval from non-owners.

## Approval is not execution

The current approve endpoint changes the task state to `approved` and records an audit event. It does not execute the task. NEXUS can separately create persisted patch proposals, collect project-owner approval/rejection and apply one approved file through the signed local companion path. Task approval does not automatically approve a patch proposal, and patch approval does not authorize terminal execution. The Studio must never present an approved task as completed.

## Remaining execution gates

Before tasks can execute autonomously, ODEI must implement:
- A task-to-proposal workflow with immutable task/proposal references and explicit per-action permissions.
- Multi-file transactional application, durable rollback journals and crash recovery; current companion apply is one file per request.
- An isolated, resource-bounded command/test runner with network, filesystem, process and time policies.
- Execution logs/artifacts, audit events, cancellation, retries and failure recovery.
- Agent orchestration with scoped workspaces, task dependencies, checkpoints and human review.
- End-to-end tests proving tenant boundaries, approval gates and execution isolation cannot be bypassed.

The task-planning UI does not expose shell, command/test execution, package installation or deployment. The separate one-file companion apply capability is not a general write or execution permission.
