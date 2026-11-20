import { describe, expect, it } from "vitest";
import type { CompanionFile } from "./companion";
import { buildWorkspaceTree } from "./workspace-tree";

const files: CompanionFile[] = [
  { path: "src/zeta.ts", size: 10 },
  { path: "README.md", size: 20 },
  { path: "src/components/App.tsx", size: 30 },
  { path: "docs/guide/intro.md", size: 40 },
  { path: "src/alpha.ts", size: 50 },
];

describe("buildWorkspaceTree", () => {
  it("groups nested relative paths and sorts directories before files", () => {
    const tree = buildWorkspaceTree(files);
    expect(tree.map((node) => [node.name, node.kind])).toEqual([
      ["docs", "directory"],
      ["src", "directory"],
      ["README.md", "file"],
    ]);
    expect(tree[1].children.map((node) => node.name)).toEqual(["components", "alpha.ts", "zeta.ts"]);
    expect(tree[1].children[0].children[0].file?.path).toBe("src/components/App.tsx");
  });

  it("preserves file metadata and supports a filtered subset", () => {
    const tree = buildWorkspaceTree(files.filter((file) => file.path.endsWith(".md")));
    expect(tree.map((node) => node.name)).toEqual(["docs", "README.md"]);
    expect(tree[0].children[0].children[0].file?.size).toBe(40);
  });

  it("resolves file/directory path collisions deterministically without duplicate tree nodes", () => {
    const conflicting = [
      { path: "a/b.txt", size: 1 },
      { path: "a", size: 2 },
    ];
    const expected = [{ name: "a", path: "a", kind: "file", file: { path: "a", size: 2 }, children: [] }];
    expect(buildWorkspaceTree(conflicting)).toEqual(expected);
    expect(buildWorkspaceTree([...conflicting].reverse())).toEqual(expected);
  });

  it("ignores unsafe or malformed relative paths", () => {
    expect(buildWorkspaceTree([
      { path: "../outside.txt", size: 1 },
      { path: "/absolute.txt", size: 2 },
      { path: "safe//empty.txt", size: 3 },
      { path: "safe/./dot.txt", size: 4 },
      { path: "safe\\windows.txt", size: 5 },
      { path: "safe/ok.txt", size: 6 },
    ]).map((node) => node.name)).toEqual(["safe"]);
    expect(buildWorkspaceTree([{ path: "safe/ok.txt", size: 6 }])[0].children[0].name).toBe("ok.txt");
  });
});
