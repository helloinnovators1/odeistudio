import type { CompanionFile } from "./companion";

const MAX_FILES = 2_000;
const MAX_FILE_BYTES = 2 * 1024 * 1024;
const MAX_TOTAL_BYTES = 40 * 1024 * 1024;
const MAX_ARCHIVE_BYTES = 50 * 1024 * 1024;
const READ_CONCURRENCY = 4;
const IGNORED_DIRECTORIES = new Set([
  ".git", ".svn", ".hg", "node_modules", ".venv", "venv", "env",
  "dist", "build", "coverage", ".next", ".nuxt", "__pycache__",
  ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
]);
const SENSITIVE_DIRECTORIES = new Set([
  ".ssh", ".aws", ".azure", ".kube", ".gnupg", ".git",
]);
const SENSITIVE_NAMES = new Set([
  ".npmrc", ".pypirc", ".netrc", ".git-credentials", "credentials",
  "credentials.json", "secrets.json", "id_rsa", "id_ed25519",
]);
const SAFE_ENV_TEMPLATES = new Set([
  ".env.example", ".env.sample", ".env.template", ".env.dist",
]);
const RESERVED_WINDOWS = new Set([
  "con", "prn", "aux", "nul", "com1", "com2", "com3", "com4", "com5",
  "com6", "com7", "com8", "com9", "lpt1", "lpt2", "lpt3", "lpt4",
  "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
]);

export interface WorkspaceArchiveResult {
  base64: string;
  fileCount: number;
  totalBytes: number;
  skippedCount: number;
  skippedPaths: string[];
}

function normalizedSafePath(path: string): string | null {
  if (!path || path.length > 1_024 || path.includes("\\") || path.startsWith("/")) return null;
  const parts = path.split("/");
  if (parts.some((part) => !part || part === "." || part === "..")) return null;
  if (parts.some((part) =>
    part.endsWith(".") || part.endsWith(" ") || /[<>:"|?*\u0000-\u001f\u007f]/.test(part)
  )) return null;
  const lower = parts.map((part) => part.toLowerCase());
  if (lower.some((part) => SENSITIVE_DIRECTORIES.has(part) || IGNORED_DIRECTORIES.has(part))) return null;
  const basename = lower.at(-1) ?? "";
  if (parts.some((part) => RESERVED_WINDOWS.has((part.split(".", 1)[0] ?? "").toLowerCase()))) return null;
  if (SENSITIVE_NAMES.has(basename)) return null;
  if (basename.startsWith(".env") && !SAFE_ENV_TEMPLATES.has(basename)) return null;
  if (basename.endsWith(".pem") || basename.endsWith(".key")
    || basename.endsWith(".p12") || basename.endsWith(".pfx") || basename.endsWith(".jks")) return null;
  if (basename.startsWith("service-account") && basename.endsWith(".json")) return null;
  if (basename.endsWith("-credentials.json")) return null;
  if (lower[0] === ".docker" && lower[1] === "config.json") return null;
  return parts.join("/");
}

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let index = 0; index < 256; index += 1) {
    let value = index;
    for (let bit = 0; bit < 8; bit += 1) {
      value = (value & 1) ? (0xedb88320 ^ (value >>> 1)) : (value >>> 1);
    }
    table[index] = value >>> 0;
  }
  return table;
})();

function crc32(bytes: Uint8Array): number {
  let value = 0xffffffff;
  for (const byte of bytes) {
    value = CRC_TABLE[(value ^ byte) & 0xff] ^ (value >>> 8);
  }
  return (value ^ 0xffffffff) >>> 0;
}

function makeHeader(size: number, signature: number): Uint8Array {
  const bytes = new Uint8Array(size);
  new DataView(bytes.buffer).setUint32(0, signature, true);
  return bytes;
}

function createZip(entries: Array<{ path: string; bytes: Uint8Array }>): Uint8Array {
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let offset = 0;
  const dosDate = 0x21;
  for (const entry of entries) {
    const name = new TextEncoder().encode(entry.path);
    if (name.byteLength > 1_024 || entry.bytes.byteLength > 0xffffffff) {
      throw new Error("A workspace file exceeds ZIP format limits.");
    }
    const checksum = crc32(entry.bytes);
    const local = makeHeader(30, 0x04034b50);
    const localView = new DataView(local.buffer);
    localView.setUint16(4, 20, true);
    localView.setUint16(6, 0x0800, true);
    localView.setUint16(8, 0, true);
    localView.setUint16(12, dosDate, true);
    localView.setUint32(14, checksum, true);
    localView.setUint32(18, entry.bytes.byteLength, true);
    localView.setUint32(22, entry.bytes.byteLength, true);
    localView.setUint16(26, name.byteLength, true);
    localView.setUint16(28, 0, true);
    localParts.push(local, name, entry.bytes);

    const central = makeHeader(46, 0x02014b50);
    const centralView = new DataView(central.buffer);
    centralView.setUint16(4, 20, true);
    centralView.setUint16(6, 20, true);
    centralView.setUint16(8, 0x0800, true);
    centralView.setUint16(10, 0, true);
    centralView.setUint16(14, dosDate, true);
    centralView.setUint32(16, checksum, true);
    centralView.setUint32(20, entry.bytes.byteLength, true);
    centralView.setUint32(24, entry.bytes.byteLength, true);
    centralView.setUint16(28, name.byteLength, true);
    centralView.setUint16(30, 0, true);
    centralView.setUint16(32, 0, true);
    centralView.setUint16(34, 0, true);
    centralView.setUint16(36, 0, true);
    centralView.setUint32(38, 0, true);
    centralView.setUint32(42, offset, true);
    centralParts.push(central, name);
    offset += local.byteLength + name.byteLength + entry.bytes.byteLength;
  }
  const centralSize = centralParts.reduce((sum, part) => sum + part.byteLength, 0);
  const end = makeHeader(22, 0x06054b50);
  const endView = new DataView(end.buffer);
  endView.setUint16(8, entries.length, true);
  endView.setUint16(10, entries.length, true);
  endView.setUint32(12, centralSize, true);
  endView.setUint32(16, offset, true);
  const all = [...localParts, ...centralParts, end];
  const total = all.reduce((sum, part) => sum + part.byteLength, 0);
  const result = new Uint8Array(total);
  let cursor = 0;
  for (const part of all) {
    result.set(part, cursor);
    cursor += part.byteLength;
  }
  return result;
}

function toBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

export async function buildWorkspaceArchive(
  files: CompanionFile[],
  readFile: (path: string) => Promise<string>,
): Promise<WorkspaceArchiveResult> {
  if (!Array.isArray(files)) throw new TypeError("Workspace file listing is invalid.");
  const selected = new Map<string, CompanionFile>();
  const skippedPaths: string[] = [];
  for (const file of files) {
    const safePath = normalizedSafePath(file.path);
    if (!safePath || !Number.isSafeInteger(file.size) || file.size < 0 || file.size > MAX_FILE_BYTES) {
      skippedPaths.push(file.path);
      continue;
    }
    const key = safePath.toLowerCase();
    if (selected.has(key) || selected.size >= MAX_FILES) {
      skippedPaths.push(file.path);
      continue;
    }
    selected.set(key, { ...file, path: safePath });
  }

  const entries: Array<{ path: string; bytes: Uint8Array }> = [];
  let totalBytes = 0;
  const candidates = [...selected.values()];
  for (let index = 0; index < candidates.length; index += READ_CONCURRENCY) {
    if (totalBytes >= MAX_TOTAL_BYTES) {
      skippedPaths.push(...candidates.slice(index).map((file) => file.path));
      break;
    }
    const batch = candidates.slice(index, index + READ_CONCURRENCY);
    const results = await Promise.all(batch.map(async (file) => {
      try {
        const content = await readFile(file.path);
        if (content.includes("\u0000")) return { file, bytes: null };
        return { file, bytes: new TextEncoder().encode(content) };
      } catch {
        return { file, bytes: null };
      }
    }));
    for (const result of results) {
      const bytes = result.bytes;
      if (!bytes || bytes.byteLength > MAX_FILE_BYTES || totalBytes + bytes.byteLength > MAX_TOTAL_BYTES) {
        skippedPaths.push(result.file.path);
        continue;
      }
      totalBytes += bytes.byteLength;
      entries.push({ path: result.file.path, bytes });
    }
  }
  if (entries.length === 0) throw new Error("No readable, safe workspace files are available to snapshot.");
  const archive = createZip(entries);
  if (archive.byteLength > MAX_ARCHIVE_BYTES) {
    throw new Error("The workspace snapshot exceeds the 50 MiB upload limit.");
  }
  return {
    base64: toBase64(archive),
    fileCount: entries.length,
    totalBytes,
    skippedCount: skippedPaths.length,
    skippedPaths: skippedPaths.slice(0, 50),
  };
}
