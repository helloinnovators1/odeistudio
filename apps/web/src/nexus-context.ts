export interface NexusContextFile {
  path: string;
  content: string;
}

export type NexusContextReader = (path: string) => Promise<string>;

export const MAX_NEXUS_CONTEXT_FILES = 5;
export const MAX_NEXUS_CONTEXT_FILE_CHARS = 8_000;
export const MAX_NEXUS_CONTEXT_TOTAL_CHARS = 40_000;

function validateRelativePath(path: string): string {
  const clean = path.trim();
  if (
    !clean || clean.length > 1_024 || clean.startsWith("/") ||
    clean.includes("\\") || clean.includes("\0") ||
    clean.split("/").some((part) => !part || part === "." || part === "..") ||
    /^[a-z]:/i.test(clean)
  ) {
    throw new TypeError("Selected context paths must be safe workspace-relative paths.");
  }
  return clean;
}

/**
 * Read only paths explicitly selected by the user. Never enumerate a workspace
 * here: the caller must provide the selected path list and an authorized reader.
 */
export async function loadNexusWorkspaceExcerpts(
  selectedPaths: string[],
  readFile: NexusContextReader,
  activeFile?: NexusContextFile | null,
): Promise<NexusContextFile[]> {
  if (!Array.isArray(selectedPaths) || selectedPaths.length < 1 || selectedPaths.length > MAX_NEXUS_CONTEXT_FILES) {
    throw new TypeError("Select between one and five workspace files.");
  }

  const normalized = selectedPaths.map(validateRelativePath);
  const seen = new Set<string>();
  for (const path of normalized) {
    const folded = path.toLocaleLowerCase("en-US");
    if (seen.has(folded)) throw new TypeError("A workspace file may only be attached once.");
    seen.add(folded);
  }

  const result: NexusContextFile[] = [];
  let total = 0;
  for (const path of normalized) {
    const content = activeFile?.path === path ? activeFile.content : await readFile(path);
    if (typeof content !== "string" || content.length > MAX_NEXUS_CONTEXT_FILE_CHARS) {
      throw new TypeError(`Selected file ${path} exceeds the 8,000-character context limit.`);
    }
    total += path.length + content.length;
    if (total > MAX_NEXUS_CONTEXT_TOTAL_CHARS) {
      throw new TypeError("Selected workspace files exceed the 40,000-character context budget.");
    }
    result.push({ path, content });
  }
  return result;
}
