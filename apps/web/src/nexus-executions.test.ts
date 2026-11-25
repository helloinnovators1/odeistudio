import { describe, expect, it, vi } from "vitest";
import {
  cancelNexusExecution,
  createNexusExecution,
  getNexusExecution,
  getNexusExecutionArtifacts,
  getNexusExecutionDiagnostics,
  listNexusExecutionEvents,
  listNexusProjectExecutions,
  listNexusExecutionProfiles,
} from "./nexus-executions";

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status, headers: { "Content-Type": "application/json" },
  });
}

describe("NEXUS execution API client", () => {
  it("loads bounded project-wide execution history with a stable cursor", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({
      runs: [{
        run_id: "run-2", organization_id: "org", project_id: "project",
        task_id: "task-2", profile_id: "python-tests", snapshot_sha256: "a".repeat(64),
        status: "completed", version: 4, attempts: 1, max_attempts: 3,
        cancel_requested: false, created_at: "2026-11-22T08:00:00Z",
        updated_at: "2026-11-22T08:01:00Z",
      }],
      has_more: true,
      next_cursor: { before_created_at: "2026-11-22T08:00:00Z", before_run_id: "run-2" },
    }));
    const page = await listNexusProjectExecutions(
      "https://api.example.test", "org", "project", "token",
      { limit: 20, cursor: { before_created_at: "2026-11-22T09:00:00Z", before_run_id: "run-3" }, fetcher },
    );
    expect(page.runs[0]?.run_id).toBe("run-2");
    expect(String(fetcher.mock.calls[0]?.[0])).toMatch(
      /^https:\/\/api\.example\.test\/api\/v1\/organizations\/org\/projects\/project\/executions\?/,
    );
    expect(page.has_more).toBe(true);
    expect(String(fetcher.mock.calls[0]?.[0])).toContain(
      "/executions?limit=20&before_created_at=2026-11-22T09%3A00%3A00Z&before_run_id=run-3",
    );
    const init = fetcher.mock.calls[0]?.[1] as RequestInit;
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer token");
    expect(init.credentials).toBe("omit");
  });

  it("rejects unsafe page sizes and incomplete history cursors before network access", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({}));
    await expect(listNexusProjectExecutions(
      "https://api.example.test", "org", "project", "token", { limit: 101, fetcher },
    )).rejects.toThrow("between 1 and 100");
    await expect(listNexusProjectExecutions(
      "https://api.example.test", "org", "project", "token",
      { cursor: { before_created_at: "", before_run_id: "run" }, fetcher },
    )).rejects.toThrow("incomplete");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("lists only server-approved execution profile identifiers", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ profiles: [{ profile_id: "python-tests" }] }));
    const profiles = await listNexusExecutionProfiles(
      "https://api.example.test/", "org/1", "project 1", "access-token", fetcher,
    );
    expect(profiles).toEqual([{ profile_id: "python-tests" }]);
    expect(fetcher.mock.calls[0]?.[0]).toBe(
      "https://api.example.test/api/v1/organizations/org%2F1/projects/project%201/execution/profiles",
    );
  });

  it("sends explicit upload and execution consent with the approved task version", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({
      run_id: "run-1", status: "queued", task_id: "task-1", profile_id: "python-tests",
      snapshot: { sha256: "a".repeat(64) },
    }));
    await createNexusExecution(
      "https://api.example.test", "org-1", "project-1", "task-1", "access-token",
      { profileId: "python-tests", expectedTaskVersion: 7, snapshotZipBase64: "UEsDBA==", repositoryPublishConsent: true },
      fetcher,
    );
    const init = fetcher.mock.calls[0]?.[1] as RequestInit;
    const body = JSON.parse(String(init.body));
    expect(body).toMatchObject({
      profile_id: "python-tests", mode: "agent", expected_task_version: 7,
      workspace_upload_consent: true, execution_consent: true,
      repository_publish_consent: true, snapshot_zip_base64: "UEsDBA==",
    });
  });

  it("uses tenant/task/run-scoped routes for status, events, cancellation and artifacts", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({}))
      .mockResolvedValueOnce(response({ run_id: "run-1", status: "running" }))
      .mockResolvedValueOnce(response({ run_id: "run-1", status: "cancelled" }))
      .mockResolvedValueOnce(response({ events: [], has_more: false, next_after_version: 4 }))
      .mockResolvedValueOnce(response({ run_id: "run-1", stdout: "redacted", stderr: "" }))
      .mockResolvedValueOnce(response({ run_id: "run", category: "failed", summary: "Execution exited with status 1.", exit_code: 1, duration_ms: 12, timed_out: false, signals: ["TEST_FAILURE"], evidence: ["FAILED test.py"], next_step: "Review evidence." }));
    await getNexusExecution("https://api.example.test", "org", "project", "task", "run", "token", fetcher);
    await cancelNexusExecution("https://api.example.test", "org", "project", "task", "run", "token", fetcher);
    await listNexusExecutionEvents("https://api.example.test", "org", "project", "task", "run", "token", 3, fetcher);
    await getNexusExecutionArtifacts("https://api.example.test", "org", "project", "task", "run", "token", fetcher);
    const diagnostics = await getNexusExecutionDiagnostics("https://api.example.test", "org", "project", "task", "run", "token", fetcher);
    expect(diagnostics.category).toBe("failed");
    expect(fetcher.mock.calls.map((call) => String(call[0]))).toEqual([
      "https://api.example.test/api/v1/organizations/org/projects/project/tasks/task/executions/run",
      "https://api.example.test/api/v1/organizations/org/projects/project/tasks/task/executions/run/cancel",
      "https://api.example.test/api/v1/organizations/org/projects/project/tasks/task/executions/run/events?after_version=3&limit=100",
      "https://api.example.test/api/v1/organizations/org/projects/project/tasks/task/executions/run/artifacts",
      "https://api.example.test/api/v1/organizations/org/projects/project/tasks/task/executions/run/diagnostics",
    ]);
  });

  it("does not leak server response internals when a request fails", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({
      detail: { code: "TASK_APPROVAL_REQUIRED", message: "Project owner approval is required." },
    }, 409));
    await expect(listNexusExecutionProfiles(
      "https://api.example.test", "org", "project", "token", fetcher,
    )).rejects.toThrow("Project owner approval is required.");
  });
  it("refuses to send bearer tokens to insecure or credentialed API origins", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ profiles: [] }));
    await expect(listNexusExecutionProfiles(
      "http://api.example.test", "org", "project", "token", fetcher,
    )).rejects.toThrow("must use HTTPS");
    await expect(listNexusExecutionProfiles(
      "https://user:password@api.example.test", "org", "project", "token", fetcher,
    )).rejects.toThrow("without URL credentials");
    expect(fetcher).not.toHaveBeenCalled();
  });
});
