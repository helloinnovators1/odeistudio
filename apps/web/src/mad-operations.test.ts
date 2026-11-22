import { describe, expect, it, vi } from "vitest";
import { getMadExecutionMetrics, listMadIncidents, transitionMadIncident } from "./mad-operations";

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}
const metrics = {
  observed_at: "2026-11-22T10:00:00Z", freshness: "fresh", worker_stale_after_seconds: 60,
  workers: { state: "healthy", known: 2, fresh: 2, stale: 0, stopping: 0 },
  queue: { state: "healthy", queued: 0, active: 1, oldest_queued_at: null },
  executions_24h: { completed: 12, failed: 1, cancelled: 2 }, alerts: [],
};
const incident = {
  id: "execution-worker-pool-unavailable", incident_id: "execution-worker-pool-unavailable",
  alert_id: "mad.execution.worker_pool_unavailable", severity: "critical",
  summary: "No worker heartbeat is fresh.", runbook: "docs/runbooks/MAD_EXECUTION_WORKERS.md",
  status: "firing", assignee: null, version: 1,
  first_seen_at: "2026-11-22T09:00:00Z", last_seen_at: "2026-11-22T09:59:00Z",
  updated_at: "2026-11-22T09:59:00Z", history: [],
};

describe("MAD operator transport", () => {
  it("loads aggregate-only metrics using a bearer without ambient credentials", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response(metrics));
    const result = await getMadExecutionMetrics("https://api.example.test/", "ephemeral-token", fetcher);
    expect(result.workers.fresh).toBe(2);
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe("https://api.example.test/api/v1/mad/execution-metrics");
    expect(init?.method).toBe("GET");
    expect(init?.credentials).toBe("omit");
    expect(init?.cache).toBe("no-store");
    expect(init?.redirect).toBe("error");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer ephemeral-token");
  });

  it("rejects malformed metrics before rendering", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response({ ...metrics, workers: { ...metrics.workers, fresh: -1 } }));
    await expect(getMadExecutionMetrics("https://api.example.test", "token", fetcher))
      .rejects.toThrow("unexpected metrics contract");
  });

  it("lists bounded, unique incident records and encodes query parameters", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response({ incidents: [incident] }));
    const result = await listMadIncidents("https://api.example.test", "token", {
      includeResolved: true, limit: 25, fetcher,
    });
    expect(result[0]?.incident_id).toBe(incident.incident_id);
    expect(fetcher.mock.calls[0]?.[0]).toBe(
      "https://api.example.test/api/v1/mad/incidents?include_resolved=true&limit=25",
    );
  });

  it("rejects duplicate or malformed incident lists and invalid page sizes", async () => {
    const duplicate = vi.fn<typeof fetch>().mockResolvedValue(response({ incidents: [incident, incident] }));
    await expect(listMadIncidents("https://api.example.test", "token", { fetcher: duplicate }))
      .rejects.toThrow("duplicate incident identities");
    const malformed = vi.fn<typeof fetch>().mockResolvedValue(response({ incidents: [{ ...incident, version: 0 }] }));
    await expect(listMadIncidents("https://api.example.test", "token", { fetcher: malformed }))
      .rejects.toThrow("unexpected incident contract");
    const never = vi.fn<typeof fetch>();
    await expect(listMadIncidents("https://api.example.test", "token", { limit: 201, fetcher: never }))
      .rejects.toThrow("between 1 and 200");
    expect(never).not.toHaveBeenCalled();
  });

  it("uses optimistic version checks for incident transitions", async () => {
    const updated = { ...incident, status: "acknowledged", version: 2 };
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response({ incident: updated }));
    const result = await transitionMadIncident("https://api.example.test", "token", incident, "acknowledge", { fetcher });
    expect(result.status).toBe("acknowledged");
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe("https://api.example.test/api/v1/mad/incidents/execution-worker-pool-unavailable/transitions");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ action: "acknowledge", expected_version: 1 });
  });

  it("validates assignee and blocks unsafe origins before sending credentials", async () => {
    const fetcher = vi.fn<typeof fetch>();
    await expect(transitionMadIncident("https://api.example.test", "token", incident, "assign", { fetcher, assignee: "../bad" }))
      .rejects.toThrow("valid assignee");
    await expect(getMadExecutionMetrics("http://api.example.test", "token", fetcher))
      .rejects.toThrow("must use HTTPS");
    await expect(getMadExecutionMetrics("https://user:secret@api.example.test", "token", fetcher))
      .rejects.toThrow("without URL credentials");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("maps authorization denial to a safe operator message", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response({
      detail: { code: "MAD_SCOPE_REQUIRED", message: "The verified identity lacks the mad:read scope." },
    }, 403));
    await expect(getMadExecutionMetrics("https://api.example.test", "token", fetcher))
      .rejects.toThrow("The verified identity lacks the mad:read scope.");
  });
});
