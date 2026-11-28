"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { readWorkspaceTextFile } = require("./workspace-files.cjs");

function identity(root) {
  const metadata = fs.statSync(root, { bigint: true });
  return { dev: metadata.dev, ino: metadata.ino, birthtimeNs: metadata.birthtimeNs };
}

function withWorkspace(run) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "odei-workspace-"));
  try {
    return run(root);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("reads a stable UTF-8 file beneath the selected workspace", () => {
  withWorkspace((root) => {
    fs.mkdirSync(path.join(root, "src"));
    fs.writeFileSync(path.join(root, "src", "main.ts"), "export const odei = true;");
    assert.equal(readWorkspaceTextFile(root, "src/main.ts", identity(root)), "export const odei = true;");
  });
});

test("rejects traversal, absolute paths, symbolic links and hard links", (t) => {
  withWorkspace((root) => {
    const outside = path.join(path.dirname(root), "odei-outside.txt");
    fs.writeFileSync(outside, "outside");
    try {
      assert.throws(() => readWorkspaceTextFile(root, "../odei-outside.txt", identity(root)), /traversal/);
      assert.throws(() => readWorkspaceTextFile(root, outside, identity(root)), /Invalid workspace-relative/);
      try {
        fs.symlinkSync(outside, path.join(root, "linked.txt"));
        assert.throws(() => readWorkspaceTextFile(root, "linked.txt", identity(root)), /Symbolic links/);
      } catch (error) {
        if (error.code === "EPERM" || error.code === "EACCES") t.skip("symlink creation is unavailable");
        else throw error;
      }
      try {
        fs.linkSync(outside, path.join(root, "hard-linked.txt"));
        assert.throws(() => readWorkspaceTextFile(root, "hard-linked.txt", identity(root)), /hard-linked|unlinked/i);
      } catch (error) {
        if (error.code === "EPERM" || error.code === "EACCES") t.skip("hard-link creation is unavailable");
        else throw error;
      }
    } finally {
      fs.rmSync(outside, { force: true });
    }
  });
});

test("rejects binary and oversized files", () => {
  withWorkspace((root) => {
    fs.writeFileSync(path.join(root, "binary.bin"), Buffer.from([0, 1, 2]));
    fs.writeFileSync(path.join(root, "large.txt"), "x".repeat(1024 * 1024 + 1));
    assert.throws(() => readWorkspaceTextFile(root, "binary.bin", identity(root)), /bounded|Binary/);
    assert.throws(() => readWorkspaceTextFile(root, "large.txt", identity(root)), /bounded/);
  });
});

test("detects in-place modification during a descriptor read", () => {
  withWorkspace((root) => {
    const file = path.join(root, "race.txt");
    fs.writeFileSync(file, "before");
    const originalRead = fs.readSync;
    let mutated = false;
    fs.readSync = function patchedRead(...args) {
      const result = originalRead.apply(this, args);
      if (result > 0 && !mutated) {
        mutated = true;
        fs.writeFileSync(file, "change");
      }
      return result;
    };
    try {
      assert.throws(() => readWorkspaceTextFile(root, "race.txt", identity(root)), /changed while being read/);
    } finally {
      fs.readSync = originalRead;
    }
  });
});

test("rejects a selected workspace root replaced during a file read", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "odei-root-race-"));
  const outside = fs.mkdtempSync(path.join(os.tmpdir(), "odei-outside-"));
  const movedRoot = root + ".original";
  const file = path.join(root, "race.txt");
  fs.writeFileSync(file, "before");
  fs.writeFileSync(path.join(outside, "race.txt"), "outside");
  const probe = path.join(outside, "symlink-probe");
  try {
    fs.symlinkSync(outside, probe, "dir");
    fs.unlinkSync(probe);
  } catch (error) {
    fs.rmSync(root, { recursive: true, force: true });
    fs.rmSync(outside, { recursive: true, force: true });
    if (error.code === "EPERM" || error.code === "EACCES") {
      t.skip("directory symlink creation is unavailable");
      return;
    }
    throw error;
  }

  const selectedIdentity = identity(root);
  const originalRead = fs.readSync;
  let swapped = false;
  let swapError = null;
  fs.readSync = function patchedRead(...args) {
    const result = originalRead.apply(this, args);
    if (result > 0 && !swapped && !swapError) {
      try {
        fs.renameSync(root, movedRoot);
        fs.symlinkSync(outside, root, "dir");
        swapped = true;
      } catch (error) {
        swapError = error;
      }
    }
    return result;
  };
  let readError = null;
  try {
    try {
      readWorkspaceTextFile(root, "race.txt", selectedIdentity);
    } catch (error) {
      readError = error;
    }
    if (swapError && ["EPERM", "EACCES", "EBUSY"].includes(swapError.code)) {
      t.skip("platform does not permit replacing an open workspace directory");
      return;
    }
    assert.equal(swapped, true);
    assert.match(String(readError), /outside the workspace|identity changed/);
  } finally {
    fs.readSync = originalRead;
    try {
      if (fs.lstatSync(root).isSymbolicLink()) fs.unlinkSync(root);
    } catch {}
    if (fs.existsSync(movedRoot) && !fs.existsSync(root)) fs.renameSync(movedRoot, root);
    fs.rmSync(root, { recursive: true, force: true });
    fs.rmSync(outside, { recursive: true, force: true });
  }
});
