import type { CompanionFile } from "./companion";

/** Filter only the already-authorized workspace listing; never performs a new filesystem read. */
export function filterWorkspaceFiles(files: CompanionFile[], query: string): CompanionFile[] {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return files;
  return files.filter((file) => file.path.toLocaleLowerCase().includes(needle));
}
