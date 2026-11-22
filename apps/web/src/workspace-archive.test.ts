import { describe, expect, it, vi } from "vitest";
import { buildWorkspaceArchive } from "./workspace-archive";

function decodeBase64(value: string): Uint8Array {
  const binary = atob(value);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

describe("safe workspace archive builder", () => {
  it("creates a valid UTF-8 stored ZIP and reports included files", async () => {
    const archive = await buildWorkspaceArchive([
      { path: "src/main.py", size: 9 },
      { path: "README.md", size: 9 },
      { path: ".env", size: 20 },
      { path: "node_modules/pkg/index.js", size: 10 },
      { path: "CON.txt", size: 3 },
    ], async (path) => path === "src/main.py" ? "print(1)\n" : "read me!\n");
    const bytes = decodeBase64(archive.base64);
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    expect(view.getUint32(0, true)).toBe(0x04034b50);
    expect(archive.fileCount).toBe(2);
    expect(archive.skippedCount).toBe(3);
    const contents = new TextDecoder().decode(bytes);
    expect(contents).toContain("src/main.py");
    expect(contents).toContain("README.md");
    expect(contents).not.toContain(".env");
    expect(contents).not.toContain("node_modules");
    expect(contents).not.toContain("CON.txt");
  });

  it("excludes credentials, traversal, duplicates and oversized files before reading", async () => {
    const read = vi.fn(async (_path: string) => "safe");
    const archive = await buildWorkspaceArchive([
      { path: "../escape", size: 4 },
      { path: "/absolute", size: 4 },
      { path: ".aws/credentials", size: 4 },
      { path: "private.pem", size: 4 },
      { path: "large.bin", size: 3 * 1024 * 1024 },
      { path: "src/a.ts", size: 4 },
      { path: "SRC/A.TS", size: 4 },
    ], read);
    expect(archive.fileCount).toBe(1);
    expect(archive.skippedCount).toBe(6);
    expect(read).toHaveBeenCalledTimes(1);
    expect(read).toHaveBeenCalledWith("src/a.ts");
  });

  it("skips unreadable files and rejects a snapshot with no readable entries", async () => {
    const archive = await buildWorkspaceArchive([
      { path: "binary.dat", size: 10 },
      { path: "src/main.py", size: 10 },
    ], async (path) => {
      if (path === "binary.dat") throw new Error("not UTF-8 text");
      return "print('ok')";
    });
    expect(archive.fileCount).toBe(1);
    expect(archive.skippedPaths).toEqual(["binary.dat"]);
    await expect(buildWorkspaceArchive(
      [{ path: "private.key", size: 5 }],
      async () => "secret",
    )).rejects.toThrow("No readable, safe workspace files");
  });

  it("does not read more than the configured workspace file count", async () => {
    const files = Array.from({ length: 2_005 }, (_, index) => ({
      path: "src/file-" + index + ".txt", size: 1,
    }));
    const read = vi.fn(async (_path: string) => "x");
    const archive = await buildWorkspaceArchive(files, read);
    expect(archive.fileCount).toBe(2_000);
    expect(archive.skippedCount).toBe(5);
    expect(read).toHaveBeenCalledTimes(2_000);
  });
  it("skips source files containing recognizable credential material", async () => {
    const archive = await buildWorkspaceArchive([
      { path: "src/main.py", size: 12 },
      { path: "config/local.ts", size: 50 },
    ], async (path) => path === "src/main.py"
      ? "print('hello')"
      : "const api_key = 'super_secret_value_that_is_long_enough';");
    expect(archive.fileCount).toBe(1);
    expect(archive.skippedCount).toBe(1);
    expect(archive.skippedPaths).toEqual(["config/local.ts"]);
  });
});
