import type { CompanionFile } from "./companion";

export interface WorkspaceTreeNode {
  name: string;
  path: string;
  kind: "directory" | "file";
  file?: CompanionFile;
  children: WorkspaceTreeNode[];
}

/** Build a deterministic, relative-path tree from an already-authorized listing. */
export function buildWorkspaceTree(files: CompanionFile[]): WorkspaceTreeNode[] {
  const roots: WorkspaceTreeNode[] = [];
  const directories = new Map<string, WorkspaceTreeNode>();

  // Stable path order makes malformed file/directory collisions deterministic.
  for (const file of [...files].sort((a, b) => a.path.localeCompare(b.path))) {
    const segments = file.path.split("/");
    if (
      segments.length === 0 ||
      segments.some((part) => !part || part === "." || part === ".." || part.includes("\\"))
    ) continue;

    let siblings = roots;
    let parentPath = "";
    for (const segment of segments.slice(0, -1)) {
      const path = parentPath ? parentPath + "/" + segment : segment;
      const conflictingFile = siblings.find((node) => node.name === segment && node.kind === "file");
      if (conflictingFile) break;
      let directory = directories.get(path);
      if (!directory) {
        directory = { name: segment, path, kind: "directory", children: [] };
        directories.set(path, directory);
        siblings.push(directory);
      }
      siblings = directory.children;
      parentPath = path;
    }

    const name = segments.at(-1)!;
    if (siblings.some((node) => node.name === name)) continue;
    siblings.push({
      name,
      path: file.path,
      kind: "file",
      file,
      children: [],
    });
  }

  const sort = (nodes: WorkspaceTreeNode[]) => {
    nodes.sort((a, b) => {
      if (a.kind !== b.kind) return a.kind === "directory" ? -1 : 1;
      return a.name.localeCompare(b.name, undefined, { sensitivity: "base", numeric: true });
    });
    for (const node of nodes) sort(node.children);
  };
  sort(roots);
  return roots;
}
