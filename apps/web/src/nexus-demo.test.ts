import { describe, expect, it } from "vitest";

import { buildNexusLocalDemoReply } from "./nexus-demo";

describe("NEXUS local chat demo", () => {
  it("returns a truthful local-only response for ask mode", () => {
    const reply = buildNexusLocalDemoReply("ask");
    expect(reply).toContain("kept only in this page’s memory");
    expect(reply).toContain("No identity provider, API, model");
  });

  it("does not imply task planning actually ran", () => {
    expect(buildNexusLocalDemoReply("plan")).toContain("task planning is disabled");
  });

  it.each(["agent", "debug"] as const)("does not claim %s tools or execution ran", (mode) => {
    const reply = buildNexusLocalDemoReply(mode);
    expect(reply).toContain("does not inspect files, call tools, execute commands");
  });
});
