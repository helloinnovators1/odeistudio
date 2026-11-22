import { describe, expect, it } from "vitest";
import { RequestGeneration } from "./request-generation";

describe("RequestGeneration", () => {
  it("allows only the newest overlapping request to commit state", () => {
    const requests = new RequestGeneration();
    const older = requests.begin();
    const newer = requests.begin();

    expect(requests.isCurrent(older)).toBe(false);
    expect(requests.isCurrent(newer)).toBe(true);
  });

  it("invalidates pending requests when the organization or session changes", () => {
    const requests = new RequestGeneration();
    const pending = requests.begin();

    requests.invalidate();

    expect(requests.isCurrent(pending)).toBe(false);
  });

  it("supports sequential requests after invalidation", () => {
    const requests = new RequestGeneration();
    const first = requests.begin();
    requests.invalidate();
    const second = requests.begin();

    expect(requests.isCurrent(first)).toBe(false);
    expect(requests.isCurrent(second)).toBe(true);
  });
});
