import { describe, expect, it } from "vitest";
import { RequestGeneration } from "./request-generation";

describe("RequestGeneration", () => {
  it("accepts only the most recently started request", () => {
    const requests = new RequestGeneration();
    const first = requests.begin();
    expect(requests.isCurrent(first)).toBe(true);
    const second = requests.begin();
    expect(requests.isCurrent(first)).toBe(false);
    expect(requests.isCurrent(second)).toBe(true);
  });

  it("invalidates an in-flight request when its selection or session changes", () => {
    const requests = new RequestGeneration();
    const pending = requests.begin();
    requests.invalidate();
    expect(requests.isCurrent(pending)).toBe(false);
  });

  it("does not accept invalid generation values", () => {
    const requests = new RequestGeneration();
    const current = requests.begin();
    expect(requests.isCurrent(Number.NaN)).toBe(false);
    expect(requests.isCurrent(-1)).toBe(false);
    expect(requests.isCurrent(current)).toBe(true);
  });
});
