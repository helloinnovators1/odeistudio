"use strict";

const fs = require("node:fs");
const path = require("node:path");

const MAX_TEXT_FILE_BYTES = 1024 * 1024;

function isWithinRoot(root, candidate) {
  const relative = path.relative(root, candidate);
  return relative !== ".."
    && !relative.startsWith(".." + path.sep)
    && !path.isAbsolute(relative);
}

function readWorkspaceTextFile(root, relativePath, expectedRootIdentity) {
  if (
    typeof relativePath !== "string"
    || !relativePath
    || relativePath.includes("\0")
    || path.isAbsolute(relativePath)
  ) {
    throw new Error("Invalid workspace-relative file path");
  }
  const parts = relativePath.replace(/\\/g, "/").split("/");
  if (parts.some((part) => !part || part === "." || part === "..")) {
    throw new Error("Path traversal is not allowed");
  }

  const canonicalRoot = fs.realpathSync(root);
  const rootMetadata = fs.statSync(canonicalRoot, { bigint: true });
  if (
    !rootMetadata.isDirectory()
    || !expectedRootIdentity
    || rootMetadata.dev !== expectedRootIdentity.dev
    || rootMetadata.ino !== expectedRootIdentity.ino
    || rootMetadata.birthtimeNs !== expectedRootIdentity.birthtimeNs
  ) {
    throw new Error("Selected workspace identity changed; select it again");
  }

  let current = canonicalRoot;
  for (const part of parts) {
    current = path.join(current, part);
    const metadata = fs.lstatSync(current, { bigint: true });
    if (metadata.isSymbolicLink()) {
      throw new Error("Symbolic links are not opened by the workspace explorer");
    }
    if (current !== path.join(canonicalRoot, ...parts) && !metadata.isDirectory()) {
      throw new Error("Workspace path contains a non-directory component");
    }
  }

  const resolved = fs.realpathSync(current);
  if (!isWithinRoot(canonicalRoot, resolved)) {
    throw new Error("Selected path is outside the workspace");
  }

  const flags = fs.constants.O_RDONLY
    | (fs.constants.O_NOFOLLOW || 0)
    | (fs.constants.O_NONBLOCK || 0);
  const descriptor = fs.openSync(resolved, flags);
  try {
    const before = fs.fstatSync(descriptor, { bigint: true });
    if (!before.isFile() || before.size > BigInt(MAX_TEXT_FILE_BYTES) || before.nlink > 1n) {
      throw new Error("Selected path is not a bounded, unlinked regular file");
    }
    const chunks = [];
    let totalBytes = 0;
    const buffer = Buffer.alloc(64 * 1024);
    while (totalBytes <= MAX_TEXT_FILE_BYTES) {
      const requested = Math.min(buffer.length, MAX_TEXT_FILE_BYTES + 1 - totalBytes);
      const bytesRead = fs.readSync(descriptor, buffer, 0, requested, null);
      if (bytesRead === 0) break;
      chunks.push(Buffer.from(buffer.subarray(0, bytesRead)));
      totalBytes += bytesRead;
    }
    if (totalBytes > MAX_TEXT_FILE_BYTES) {
      throw new Error("Selected file exceeds the 1 MB text editor limit");
    }
    const content = Buffer.concat(chunks, totalBytes);
    const after = fs.fstatSync(descriptor, { bigint: true });
    let verifyPath = canonicalRoot;
    for (let index = 0; index < parts.length; index += 1) {
      verifyPath = path.join(verifyPath, parts[index]);
      const componentMetadata = fs.lstatSync(verifyPath, { bigint: true });
      if (
        componentMetadata.isSymbolicLink()
        || (index < parts.length - 1 && !componentMetadata.isDirectory())
      ) {
        throw new Error("Selected workspace identity changed: a path component became a symbolic link");
      }
      if (
        index === parts.length - 1
        && (componentMetadata.dev !== before.dev || componentMetadata.ino !== before.ino)
      ) {
        throw new Error("Selected workspace identity changed: file path changed while being read");
      }
    }
    const resolvedAgain = fs.realpathSync(current);
    if (!isWithinRoot(canonicalRoot, resolvedAgain)) {
      throw new Error("Selected path changed outside the workspace while being read");
    }
    const pathMetadata = fs.statSync(resolvedAgain, { bigint: true });
    const rootResolvedAgain = fs.realpathSync(root);
    const rootMetadataAfter = fs.statSync(rootResolvedAgain, { bigint: true });
    if (
      rootResolvedAgain !== canonicalRoot
      || rootMetadataAfter.dev !== expectedRootIdentity.dev
      || rootMetadataAfter.ino !== expectedRootIdentity.ino
      || rootMetadataAfter.birthtimeNs !== expectedRootIdentity.birthtimeNs
    ) {
      throw new Error("Selected workspace identity changed while reading");
    }
    const stableFields = ["dev", "ino", "mode", "size", "mtimeNs", "ctimeNs"];
    if (
      stableFields.some((field) => before[field] !== after[field])
      || before.dev !== pathMetadata.dev
      || before.ino !== pathMetadata.ino
      || content.length !== Number(after.size)
    ) {
      throw new Error("Workspace file changed while being read");
    }
    if (content.includes(0)) throw new Error("Binary files cannot be opened in the text editor");
    return content.toString("utf8");
  } finally {
    fs.closeSync(descriptor);
  }
}


const LIST_LIMITS = Object.freeze({
  files: 5000, bytes: 50 * 1024 * 1024, fileBytes: 2 * 1024 * 1024,
  directories: 5000, entries: 100000, depth: 64,
});
const IGNORED_DIRECTORIES = new Set([
  ".git", "node_modules", ".next", "dist", "build", "coverage",
  ".turbo", ".venv", "__pycache__",
]);

function assertSelectedRoot(root, expectedRootIdentity) {
  const canonicalRoot = fs.realpathSync(root);
  const metadata = fs.statSync(canonicalRoot, { bigint: true });
  if (
    !metadata.isDirectory() || !expectedRootIdentity
    || metadata.dev !== expectedRootIdentity.dev
    || metadata.ino !== expectedRootIdentity.ino
    || metadata.birthtimeNs !== expectedRootIdentity.birthtimeNs
  ) throw new Error("Selected workspace identity changed; select it again");
  return canonicalRoot;
}

function assertStableDirectory(root, directory, before) {
  const metadata = fs.lstatSync(directory, { bigint: true });
  if (metadata.isSymbolicLink() || !metadata.isDirectory()) {
    throw new Error("Workspace directory changed during enumeration");
  }
  const resolved = fs.realpathSync(directory);
  if (!isWithinRoot(root, resolved) || resolved !== directory) {
    throw new Error("Workspace directory escaped the selected root");
  }
  const after = fs.lstatSync(resolved, { bigint: true });
  if (
    metadata.dev !== before.dev || metadata.ino !== before.ino
    || metadata.mtimeNs !== before.mtimeNs || metadata.ctimeNs !== before.ctimeNs
    || after.dev !== before.dev || after.ino !== before.ino
  ) throw new Error("Workspace directory changed during enumeration");
  return metadata;
}

function listWorkspaceFiles(root, expectedRootIdentity) {
  const canonicalRoot = assertSelectedRoot(root, expectedRootIdentity);
  const files = [];
  const pending = [{ relative: "", depth: 0 }];
  let totalBytes = 0, visitedDirectories = 0, inspectedEntries = 0;

  while (pending.length && files.length < LIST_LIMITS.files && totalBytes < LIST_LIMITS.bytes) {
    const current = pending.pop();
    const absolute = current.relative ? path.join(canonicalRoot, current.relative) : canonicalRoot;
    const before = fs.lstatSync(absolute, { bigint: true });
    if (before.isSymbolicLink() || !before.isDirectory()) {
      throw new Error("Workspace directory changed before enumeration");
    }
    const resolvedBefore = fs.realpathSync(absolute);
    if (!isWithinRoot(canonicalRoot, resolvedBefore) || resolvedBefore !== absolute) {
      throw new Error("Workspace directory escaped the selected root");
    }
    if (++visitedDirectories > LIST_LIMITS.directories) {
      throw new Error("Workspace contains too many directories to enumerate safely");
    }
    if (current.depth > LIST_LIMITS.depth) {
      throw new Error("Workspace directory nesting exceeds the safe limit");
    }

    const entries = fs.readdirSync(absolute, { withFileTypes: true })
      .sort((a, b) => a.name.localeCompare(b.name));
    assertStableDirectory(canonicalRoot, absolute, before);

    for (const entry of entries) {
      if (++inspectedEntries > LIST_LIMITS.entries) {
        throw new Error("Workspace contains too many entries to enumerate safely");
      }
      if (IGNORED_DIRECTORIES.has(entry.name)) continue;
      const childRelative = current.relative ? path.join(current.relative, entry.name) : entry.name;
      const childAbsolute = path.join(canonicalRoot, childRelative);
      const metadata = fs.lstatSync(childAbsolute, { bigint: true });
      if (metadata.isSymbolicLink()) continue;

      if (metadata.isDirectory()) {
        const resolved = fs.realpathSync(childAbsolute);
        if (!isWithinRoot(canonicalRoot, resolved) || resolved !== childAbsolute) {
          throw new Error("Workspace directory escaped the selected root");
        }
        if (current.depth >= LIST_LIMITS.depth) {
          throw new Error("Workspace directory nesting exceeds the safe limit");
        }
        pending.push({ relative: childRelative, depth: current.depth + 1 });
      } else if (
        metadata.isFile() && metadata.nlink === 1n
        && metadata.size <= BigInt(LIST_LIMITS.fileBytes)
      ) {
        const resolved = fs.realpathSync(childAbsolute);
        if (!isWithinRoot(canonicalRoot, resolved) || resolved !== childAbsolute) {
          throw new Error("Workspace file escaped the selected root");
        }
        const after = fs.lstatSync(childAbsolute, { bigint: true });
        if (
          after.isSymbolicLink() || !after.isFile()
          || after.dev !== metadata.dev || after.ino !== metadata.ino
          || after.size !== metadata.size
        ) throw new Error("Workspace file changed during enumeration");
        files.push({ path: childRelative.split(path.sep).join("/"), size: Number(after.size) });
        totalBytes += Number(after.size);
        if (files.length >= LIST_LIMITS.files || totalBytes >= LIST_LIMITS.bytes) break;
      }
    }
  }
  assertSelectedRoot(root, expectedRootIdentity);
  return files.sort((a, b) => a.path.localeCompare(b.path));
}

module.exports = { readWorkspaceTextFile, listWorkspaceFiles };
