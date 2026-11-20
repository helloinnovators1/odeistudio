import { describe, expect, it } from "vitest";
import { filterWorkspaceFiles } from "./workspace-filter";
import type { CompanionFile } from "./companion";

const files: CompanionFile[] = [
  { path: "src/App.tsx", size: 120 },
  { path: "docs/README.md", size: 80 },
  { path: "apps/api/main.py", size: 240 },
];

describe("filterWorkspaceFiles", () => {
  it("returns the original listing for an empty query", () => {
    expect(filterWorkspaceFiles(files, "  ")).toBe(files);
  });

  it("matches paths case-insensitively across directories and extensions", () => {
    expect(filterWorkspaceFiles(files, "APP")).toEqual([files[0]]);
    expect(filterWorkspaceFiles(files, ".PY")).toEqual([files[2]]);
    expect(filterWorkspaceFiles(files, "docs/")).toEqual([files[1]]);
  });

  it("returns an empty list when no path matches", () => {
    expect(filterWorkspaceFiles(files, "missing")).toEqual([]);
  });
});
