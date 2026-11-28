const path = require("node:path");
const os = require("node:os");
const fs = require("node:fs");
const { execFile } = require("node:child_process");
const { promisify } = require("node:util");
const { app, BrowserWindow, WebContentsView, dialog, ipcMain, shell } = require("electron");
const pty = require("node-pty");
const { isTrustedAppUrl } = require("./security.cjs");
const { readWorkspaceTextFile, listWorkspaceFiles } = require("./workspace-files.cjs");

const execFileAsync = promisify(execFile);
const APP_URL = process.env.ODEI_DESKTOP_URL || "https://zurios.vercel.app/odeistudio?window=ide";
if (!isTrustedAppUrl(APP_URL)) {
  throw new Error("ODEI_DESKTOP_URL must use the ODEI production route or an explicit localhost development origin");
}
const MAX_TERMINALS = 4;
const terminals = new Map();
let mainWindow;
let selectedWorkspace = null;
let selectedWorkspaceIdentity = null;
let browserView = null;
let browserState = { url: "about:blank", canGoBack: false, canGoForward: false, loading: false };

function trusted(event) {
  if (!mainWindow || event.sender !== mainWindow.webContents || event.senderFrame !== event.sender.mainFrame) {
    throw new Error("Untrusted ODEI desktop IPC sender");
  }
  if (!isTrustedAppUrl(event.senderFrame.url)) {
    throw new Error("ODEI desktop API is unavailable outside the trusted ODEI application route");
  }
}
function handle(channel, fn) {
  ipcMain.handle(channel, async (event, ...args) => { trusted(event); return fn(...args); });
}
function safeWebUrl(value) {
  const url = new URL(String(value));
  if (!["http:", "https:"].includes(url.protocol)) throw new Error("Only HTTP and HTTPS URLs are allowed");
  return url.toString();
}
function requireWorkspace() {
  if (!selectedWorkspace || !selectedWorkspaceIdentity) {
    throw new Error("Select a local workspace first");
  }
  let resolved;
  let metadata;
  try {
    resolved = fs.realpathSync(selectedWorkspace);
    metadata = fs.statSync(resolved, { bigint: true });
  } catch {
    selectedWorkspace = null;
    selectedWorkspaceIdentity = null;
    throw new Error("The selected workspace is no longer available");
  }
  if (
    resolved !== selectedWorkspace
    || !metadata.isDirectory()
    || metadata.dev !== selectedWorkspaceIdentity.dev
    || metadata.ino !== selectedWorkspaceIdentity.ino
    || metadata.birthtimeNs !== selectedWorkspaceIdentity.birthtimeNs
  ) {
    selectedWorkspace = null;
    selectedWorkspaceIdentity = null;
    throw new Error("The selected workspace identity changed; select it again");
  }
  return selectedWorkspace;
}
async function git(args, options = {}) {
  const cwd = requireWorkspace();
  try {
    const result = await execFileAsync("git", ["-C", cwd, ...args], {
      cwd, windowsHide: true, timeout: 15000, maxBuffer: 4 * 1024 * 1024,
      env: { ...process.env, GIT_OPTIONAL_LOCKS: "0", GIT_TERMINAL_PROMPT: "0" },
      ...options,
    });
    return result.stdout;
  } catch (error) {
    const detail = String(error.stderr || error.message || "Git operation failed").slice(0, 4000);
    throw new Error(detail);
  }
}
function validateGitPaths(paths) {
  if (!Array.isArray(paths) || paths.length < 1 || paths.length > 100) throw new Error("Select between 1 and 100 paths");
  return paths.map((item) => {
    if (typeof item !== "string" || !item || item.includes("\0") || path.isAbsolute(item)) throw new Error("Invalid repository-relative path");
    const normalized = item.replace(/\\/g, "/");
    if (normalized.split("/").some((part) => part === ".." || part === "")) throw new Error("Path traversal is not allowed");
    return normalized;
  });
}
function readDesktopSettings() {
  const file = path.join(app.getPath("userData"), "odei-settings.json");
  try {
    const parsed = JSON.parse(fs.readFileSync(file, "utf8"));
    return { odidSignInEnabled: parsed?.odidSignInEnabled === true };
  } catch {
    return { odidSignInEnabled: false };
  }
}
function writeDesktopSettings(settings) {
  if (!settings || typeof settings.odidSignInEnabled !== "boolean") {
    throw new Error("ODID sign-in setting must be a boolean");
  }
  const directory = app.getPath("userData");
  const file = path.join(directory, "odei-settings.json");
  const temporary = file + ".tmp";
  const contents = JSON.stringify({ odidSignInEnabled: settings.odidSignInEnabled }, null, 2) + "\n";
  fs.writeFileSync(temporary, contents, { encoding: "utf8", mode: 0o600 });
  try { fs.chmodSync(temporary, 0o600); } catch {}
  fs.renameSync(temporary, file);
  return { odidSignInEnabled: settings.odidSignInEnabled };
}

function publishBrowserState() {
  if (!browserView || !mainWindow) return;
  browserState = {
    url: browserView.webContents.getURL(),
    canGoBack: browserView.webContents.canGoBack(),
    canGoForward: browserView.webContents.canGoForward(),
    loading: browserView.webContents.isLoading(),
  };
  mainWindow.webContents.send("odei:browser:state", browserState);
}
function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1440, height: 900, minWidth: 760, minHeight: 560,
    title: "OIPTECH Core",
    backgroundColor: "#f3f4f6",
    autoHideMenuBar: true,
    titleBarStyle: "hidden",
    titleBarOverlay: { color: "#f3f4f6", symbolColor: "#59616b", height: 38 },
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      spellcheck: true,
    },
  });
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    try { void shell.openExternal(safeWebUrl(url)); } catch {}
    return { action: "deny" };
  });
  mainWindow.webContents.on("will-navigate", (event, target) => {
    if (!isTrustedAppUrl(target)) event.preventDefault();
  });
  mainWindow.webContents.on("will-redirect", (event, target) => {
    if (!isTrustedAppUrl(target)) event.preventDefault();
  });
  mainWindow.on("closed", () => {
    for (const terminal of terminals.values()) terminal.kill();
    terminals.clear();
    if (browserView) { browserView.webContents.close(); browserView = null; }
    mainWindow = null;
  });
  mainWindow.loadURL(APP_URL);
}

handle("odei:settings:get", () => readDesktopSettings());
handle("odei:settings:set-odid-sign-in", (enabled) => {
  if (typeof enabled !== "boolean") throw new Error("ODID sign-in setting must be a boolean");
  return writeDesktopSettings({ ...readDesktopSettings(), odidSignInEnabled: enabled });
});

handle("odei:window:minimize", () => { mainWindow.minimize(); return true; });
handle("odei:window:toggle-maximize", () => {
  if (mainWindow.isMaximized()) mainWindow.unmaximize(); else mainWindow.maximize();
  return mainWindow.isMaximized();
});
handle("odei:window:close", () => { mainWindow.close(); return true; });
handle("odei:window:state", () => ({ minimized: mainWindow.isMinimized(), maximized: mainWindow.isMaximized(), focused: mainWindow.isFocused() }));


handle("odei:workspace:select", async () => {
  const result = await dialog.showOpenDialog(mainWindow, { title: "Open ODEI workspace", properties: ["openDirectory", "createDirectory"] });
  if (result.canceled || !result.filePaths[0]) return null;
  const selectedPath = fs.realpathSync(result.filePaths[0]);
  const metadata = fs.statSync(selectedPath, { bigint: true });
  if (!metadata.isDirectory()) {
    throw new Error("The selected workspace is not a directory");
  }
  selectedWorkspace = selectedPath;
  selectedWorkspaceIdentity = {
    dev: metadata.dev, ino: metadata.ino, birthtimeNs: metadata.birthtimeNs,
  };
  return { name: path.basename(selectedWorkspace) };
});
handle("odei:workspace:current", () => selectedWorkspace
  ? ({ name: path.basename(requireWorkspace()) })
  : null);
handle("odei:workspace:files", () => listWorkspaceFiles(requireWorkspace(), selectedWorkspaceIdentity));
handle("odei:workspace:read-file", (relativePath) => (
  readWorkspaceTextFile(requireWorkspace(), relativePath, selectedWorkspaceIdentity)
));

handle("odei:git:status", async () => {
  const root = (await git(["rev-parse", "--show-toplevel"])).trim();
  const selected = fs.realpathSync(requireWorkspace());
  if (fs.realpathSync(root) !== selected) throw new Error("Select the repository root, not a parent or nested folder");
  const branch = (await git(["branch", "--show-current"])).trim() || "(detached HEAD)";
  const raw = await git(["status", "--porcelain=v1", "--untracked-files=all"]);
  const files = raw.split(/\r?\n/).filter(Boolean).map((line) => ({
    index: line.slice(0, 1), worktree: line.slice(1, 2), path: line.slice(3),
    staged: line[0] !== " " && line[0] !== "?", unstaged: line[1] !== " ",
    untracked: line.startsWith("??"),
  }));
  return { branch, files, clean: files.length === 0 };
});
handle("odei:git:diff", async (filePath) => {
  const args = ["diff", "--no-ext-diff", "--no-color"];
  if (filePath) args.push("--", ...validateGitPaths([filePath]));
  const [unstaged, staged] = await Promise.all([
    git(args), git(["diff", "--cached", "--no-ext-diff", "--no-color", ...(filePath ? ["--", ...validateGitPaths([filePath])] : [])]),
  ]);
  return { unstaged, staged };
});
handle("odei:git:stage", async (paths) => {
  const safe = validateGitPaths(paths);
  await git(["add", "--", ...safe]);
  return { staged: safe };
});
handle("odei:git:unstage", async (paths) => {
  const safe = validateGitPaths(paths);
  await git(["reset", "--", ...safe]);
  return { unstaged: safe };
});
handle("odei:git:commit", async (message) => {
  if (typeof message !== "string" || !message.trim() || message.length > 500) throw new Error("Enter a commit message (maximum 500 characters)");
  await git(["commit", "-m", message.trim()]);
  return { commit: (await git(["rev-parse", "HEAD"])).trim(), summary: (await git(["show", "--no-patch", "--format=%s", "HEAD"])).trim() };
});

handle("odei:browser:create", () => {
  if (browserView) return browserState;
  browserView = new WebContentsView({ webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true } });
  browserView.webContents.setWindowOpenHandler(({ url }) => {
    try { void shell.openExternal(safeWebUrl(url)); } catch {}
    return { action: "deny" };
  });
  browserView.webContents.on("will-navigate", (event, target) => {
    try { safeWebUrl(target); } catch { event.preventDefault(); }
  });
  for (const event of ["did-navigate", "did-navigate-in-page", "did-start-loading", "did-stop-loading", "did-fail-load"]) {
    browserView.webContents.on(event, publishBrowserState);
  }
  mainWindow.contentView.addChildView(browserView);
  browserView.setBounds({ x: 0, y: 0, width: 0, height: 0 });
  return browserState;
});
handle("odei:browser:navigate", async (value) => {
  if (!browserView) throw new Error("Create the native browser view first");
  const url = safeWebUrl(value);
  await browserView.webContents.loadURL(url);
  publishBrowserState();
  return browserState;
});
handle("odei:browser:back", () => { if (browserView?.webContents.canGoBack()) browserView.webContents.goBack(); return true; });
handle("odei:browser:forward", () => { if (browserView?.webContents.canGoForward()) browserView.webContents.goForward(); return true; });
handle("odei:browser:reload", () => { browserView?.webContents.reload(); return true; });
handle("odei:browser:set-bounds", (bounds) => {
  if (!browserView || !bounds || ![bounds.x, bounds.y, bounds.width, bounds.height].every(Number.isFinite)) return false;
  const x = Math.max(0, Math.round(bounds.x)), y = Math.max(0, Math.round(bounds.y));
  const width = Math.max(0, Math.min(10000, Math.round(bounds.width)));
  const height = Math.max(0, Math.min(10000, Math.round(bounds.height)));
  browserView.setBounds({ x, y, width, height });
  return true;
});
handle("odei:browser:close", () => {
  if (browserView) { mainWindow.contentView.removeChildView(browserView); browserView.webContents.close(); browserView = null; }
  return true;
});
handle("odei:open-external", async (value) => { await shell.openExternal(safeWebUrl(value)); return true; });

handle("odei:terminal:open", (options = {}) => {
  const cwd = requireWorkspace();
  if (terminals.size >= MAX_TERMINALS) throw new Error("Maximum of four terminal sessions reached");
  const cols = Math.max(40, Math.min(300, Number(options.cols) || 100));
  const rows = Math.max(10, Math.min(100, Number(options.rows) || 28));
  const shellPath = process.platform === "win32" ? (process.env.ComSpec || "powershell.exe") : (process.env.SHELL || "/bin/bash");
  const id = require("node:crypto").randomUUID();
  const terminal = pty.spawn(shellPath, [], {
    name: "xterm-256color", cols, rows, cwd,
    env: { ...process.env, TERM: "xterm-256color" },
  });
  terminals.set(id, terminal);
  terminal.onData((data) => mainWindow?.webContents.send("odei:terminal:data", { id, data }));
  terminal.onExit(({ exitCode }) => { terminals.delete(id); mainWindow?.webContents.send("odei:terminal:data", { id, exitCode }); });
  return { id, cwd: path.basename(cwd), shell: path.basename(shellPath) };
});
handle("odei:terminal:write", (id, data) => {
  const terminal = terminals.get(id);
  if (!terminal || typeof data !== "string" || data.length > 65536) throw new Error("Terminal session or input is invalid");
  terminal.write(data); return true;
});
handle("odei:terminal:resize", (id, cols, rows) => {
  const terminal = terminals.get(id);
  if (!terminal) throw new Error("Terminal session not found");
  terminal.resize(Math.max(40, Math.min(300, Math.floor(cols))), Math.max(10, Math.min(100, Math.floor(rows))));
  return true;
});
handle("odei:terminal:close", (id) => { const terminal = terminals.get(id); if (terminal) { terminal.kill(); terminals.delete(id); } return true; });

app.whenReady().then(() => {
  createMainWindow();
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createMainWindow(); });
});
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
