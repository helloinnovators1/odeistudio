import { describe, expect, it, vi } from "vitest";
import {
  cancelNexusExecution,
  createNexusExecution,
  getNexusExecution,
  getNexusExecutionArtifacts,
  listNexusExecutionEvents,
  listNexusExecutionProfiles,
} from "./nexus-executions";

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status, headers: { "Content-Type": "application/json" },
  });
}

describe("NEXUS execution API client", () => {
  it("lists only server-approved execution profile identifiers", async () => {
    const fetcher = vi.fn(async () => response({ profiles: [{ profile_id: "python-tests" }] }));
    const profiles = await listNexusExecutionProfiles(
      "https://api.example.test/", "org/1", "project 1", "access-token", fetcher,
    );
    expect(profiles).toEqual([{ profile_id: "python-tests" }]);
    expect(fetcher.mock.calls[0]?.[0]).toBe(
      "https://api.example.test/api/v1/organizations/org%2F1/projects/project%201/execution/profiles",
    );
  });

  it("sends explicit upload and execution consent with the approved task version", async () => {
    const fetcher = vi.fn(async () => response({
      run_id: "run-1", status: "queued", task_id: "task-1", profile_id: "python-tests",
      snapshot: { sha256: "a".repeat(64) },
    }));
    await createNexusExecution(
      "https://api.example.test", "org-1", "project-1", "task-1", "access-token",
      { profileId: "python-tests", expectedTaskVersion: 7, snapshotZipBase64: "UEsDBA==" },
      fetcher,
    );
    const init = fetcher.mock.calls[0]?.[1] as RequestInit;
    const body = JSON.parse(String(init.body));
    expect(body).toMatchObject({
      profile_id: "python-tests", expected_task_version: 7,
      workspace_upload_consent: true, execution_consent: true,
      snapshot_zip_base64: "UEsDBA==",
    });
  });

  it("uses tenant/task/run-scoped routes for status, events, cancellation and artifacts", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ run_id: "run-1", status: "running" }))
      .mockResolvedValueOnce(response({ run_id: "run-1", status: "cancelled" }))
      .mockResolvedValueOnce(response({ events: [], has_more: false, next_after_version: 4 }))
      .mockResolvedValueOnce(response({ run_id: "run-1", stdout: "redacted", stderr: "" }));
    await getNexusExecution("https://api.example.test", "org", "project", "task", "run", "token", fetcher);
    await cancelNexusExecution("https://api.example.test", "org", "project", "task", "run", "token", fetcher);
    await listNexusExecutionEvents("https://api.example.test", "org", "project", "task", "run", "token", 3, fetcher);
    await getNexusExecutionArtifacts("https://api.example.test", "org", "project", "task", "run", "token", fetcher);
    expect(fetcher.mock.calls.map((call) => String(call[0]))).toEqual([
      "https://api.example.test/api/v1/organizations/org/projects/project/tasks/task/executions/run",
      "https://api.example.test/api/v1/organizations/org/projects/project/tasks/task/executions/run/cancel",
      "https://api.example.test/api/v1/organizations/org/projects/project/tasks/task/executions/run/events?after_version=3&limit=100",
      "https://api.example.test/api/v1/organizations/org/projects/project/tasks/task/executions/run/artifacts",
    ]);
  });

  it("does not leak server response internals when a request fails", async () => {
    const fetcher = vi.fn(async () => response({
      detail: { code: "TASK_APPROVAL_REQUIRED", message: "Project owner approval is required." },
    }, 409));
    await expect(listNexusExecutionProfiles(
      "https://api.example.test", "org", "project", "token", fetcher,
    )).rejects.toThrow("Project owner approval is required.");
  });
});
