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

The current approve endpoint changes the task state to `approved` and records an audit event. It does not apply code changes, create patch proposals, write files, execute commands, run tests or deploy software. The Studio must never present an approved task as completed.

## Remaining execution gates

Before tasks can execute, ODEI must implement:
- Explicit tool permissions and scoped workspace handles.
- Durable patch proposals with immutable base snapshots and content hashes.
- Human review and approval of each proposed change.
- Atomic, path-safe application with rollback and recovery records.
- An isolated, resource-bounded command/test runner.
- Execution logs, audit events, cancellation and failure recovery.
- End-to-end tests proving that tenant boundaries and approval gates cannot be bypassed.

No shell, file-write or deployment capability is enabled by the current task-planning UI.
