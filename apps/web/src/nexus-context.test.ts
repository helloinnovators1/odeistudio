import { describe, expect, it, vi } from "vitest";
import { loadNexusWorkspaceExcerpts } from "./nexus-context";

describe("loadNexusWorkspaceExcerpts", () => {
  it("reads only explicitly selected files and preserves their order", async () => {
    const readFile = vi.fn(async (path: string) => `contents of ${path}`);
    const result = await loadNexusWorkspaceExcerpts(
      ["src/main.ts", "apps/api/main.py"], readFile,
    );
    expect(result).toEqual([
      { path: "src/main.ts", content: "contents of src/main.ts" },
      { path: "apps/api/main.py", content: "contents of apps/api/main.py" },
    ]);
    expect(readFile).toHaveBeenCalledTimes(2);
    expect(readFile).toHaveBeenNthCalledWith(1, "src/main.ts");
  });

  it("uses the current editor buffer instead of a potentially stale disk read", async () => {
    const readFile = vi.fn(async () => "stale disk contents");
    const result = await loadNexusWorkspaceExcerpts(
      ["src/main.ts"], readFile,
      { path: "src/main.ts", content: "unsaved editor buffer" },
    );
    expect(result[0]?.content).toBe("unsaved editor buffer");
    expect(readFile).not.toHaveBeenCalled();
  });

  it("rejects an empty, oversized, duplicate or unsafe selection before reading", async () => {
    const readFile = vi.fn(async () => "content");
    await expect(loadNexusWorkspaceExcerpts([], readFile)).rejects.toThrow("one and five");
    await expect(loadNexusWorkspaceExcerpts(
      Array.from({ length: 6 }, (_, index) => `${index}.ts`), readFile,
    )).rejects.toThrow("one and five");
    await expect(loadNexusWorkspaceExcerpts(["src/main.ts", "SRC/MAIN.TS"], readFile))
      .rejects.toThrow("only be attached once");
    await expect(loadNexusWorkspaceExcerpts(["../secret.env"], readFile))
      .rejects.toThrow("workspace-relative");
    expect(readFile).not.toHaveBeenCalled();
  });

  it("passes the active cancellation signal to companion file reads", async () => {
    const controller = new AbortController();
    const readFile = vi.fn(async (_path: string, _signal?: AbortSignal) => "content");
    await loadNexusWorkspaceExcerpts(["src/main.ts"], readFile, null, controller.signal);
    expect(readFile).toHaveBeenCalledWith("src/main.ts", controller.signal);
  });

  it("excludes credential files, sensitive directories and private-key formats", async () => {
    const readFile = vi.fn(async () => "must not read");
    for (const path of [
      ".env", ".env.staging", ".ssh/id_ed25519", ".aws/credentials",
      ".git/config", "secrets.json", "config/service.pem", "private/client.key",
    ]) {
      await expect(loadNexusWorkspaceExcerpts([path], readFile))
        .rejects.toThrow("workspace-relative");
    }
    expect(readFile).not.toHaveBeenCalled();
  });

  it("rejects null bytes and cancelled context reads", async () => {
    const readFile = vi.fn(async () => "should not be read");
    await expect(loadNexusWorkspaceExcerpts(["src/" + String.fromCharCode(0) + "main.ts"], readFile))
      .rejects.toThrow("workspace-relative");
    const controller = new AbortController();
    controller.abort();
    await expect(loadNexusWorkspaceExcerpts(
      ["src/main.ts"], readFile, null, controller.signal,
    )).rejects.toThrow("cancelled");
    expect(readFile).not.toHaveBeenCalled();
  });

  it("rejects files over 8,000 characters and aggregate context over 40,000", async () => {
    await expect(loadNexusWorkspaceExcerpts(
      ["large.ts"], async () => "x".repeat(8_001),
    )).rejects.toThrow("8,000-character");
    await expect(loadNexusWorkspaceExcerpts(
      ["a.ts", "b.ts", "c.ts", "d.ts", "e.ts"],
      async () => "x".repeat(8_000),
    )).rejects.toThrow("40,000-character");
  });
});
