import { useEffect, useMemo, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import MonacoEditor from "@monaco-editor/react";
import NexusChatPanel from "./NexusChatPanel";
import {
  connectToCompanion,
  disconnectFromCompanion,
  listWorkspaces,
  listWorkspaceFiles,
  pairWithCompanion,
  previewWorkspacePatch,
  readWorkspaceFile,
  type CompanionFile,
  type CompanionWorkspace,
} from "./companion";
import { formatBytes } from "./file-utils";
import { filterWorkspaceFiles } from "./workspace-filter";
import { buildWorkspaceTree, type WorkspaceTreeNode } from "./workspace-tree";
import {
  isToggleNexusChatShortcut,
  languageForPath,
  readChatPanelSide,
  writeChatPanelSide,
  type ChatPanelSide,
} from "./ide-preferences";
import "./styles.css";

interface OpenTab {
  path: string;
  content: string;
}

export default function App() {
  const [connected, setConnected] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [workspaces, setWorkspaces] = useState<CompanionWorkspace[]>([]);
  const [workspace, setWorkspace] = useState("");
  const [files, setFiles] = useState<CompanionFile[]>([]);
  const [fileQuery, setFileQuery] = useState("");
  const [collapsedFolders, setCollapsedFolders] = useState<Set<string>>(() => new Set());
  const [tabs, setTabs] = useState<OpenTab[]>([]);
  const [activePath, setActivePath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("Connect the local companion to open a workspace.");
  const [chatOpen, setChatOpen] = useState(() => {
    try {
      const callback = new URL(import.meta.env.VITE_ODID_REDIRECT_URI);
      return window.location.origin === callback.origin
        && window.location.pathname === callback.pathname
        && Boolean(window.location.search);
    } catch {
      return false;
    }
  });
  const [chatSide, setChatSide] = useState<ChatPanelSide>(() => readChatPanelSide());
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [bottomPanel, setBottomPanel] = useState<"output" | "problems" | "terminal">("output");
  const [patchDialogOpen, setPatchDialogOpen] = useState(false);
  const [patchDraft, setPatchDraft] = useState("");
  const [patchDiff, setPatchDiff] = useState<string | null>(null);
  const [patchPreviewBusy, setPatchPreviewBusy] = useState(false);
  const [patchPreviewError, setPatchPreviewError] = useState("");

  const activeTab = useMemo(
    () => tabs.find((tab) => tab.path === activePath) ?? null,
    [tabs, activePath],
  );
  const workspaceName = workspaces.find((item) => item.workspace_id === workspace)?.name ?? "No folder open";
  const visibleFiles = useMemo(() => filterWorkspaceFiles(files, fileQuery), [files, fileQuery]);
  const workspaceTree = useMemo(() => buildWorkspaceTree(visibleFiles), [visibleFiles]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (isToggleNexusChatShortcut(event)) {
        event.preventDefault();
        setChatOpen((open) => !open);
        return;
      }
      if ((event.metaKey || event.ctrlKey) && !event.altKey && event.key.toLowerCase() === "s") {
        event.preventDefault();
        setMessage("This workspace is read-only. Saving and file writes are not enabled yet.");
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  async function connect() {
    setBusy(true);
    setError("");
    try {
      await connectToCompanion();
      setConnected(true);
      setMessage("Companion found. Enter the one-time code shown in its local console.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Connection failed.");
    } finally {
      setBusy(false);
    }
  }

  async function pair() {
    if (!code.trim()) {
      setError("Enter the pairing code.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const session = await pairWithCompanion(code.trim());
      let selectedWorkspaces: CompanionWorkspace[];
      try {
        selectedWorkspaces = await listWorkspaces(session.access_token);
      } catch (cause) {
        await disconnectFromCompanion(session.access_token).catch(() => undefined);
        throw cause;
      }
      setToken(session.access_token);
      setWorkspaces(selectedWorkspaces);
      setCode("");
      setMessage("Paired. Select a folder that you explicitly chose in the companion.");
    } catch (cause) {
      setToken(null);
      setError(cause instanceof Error ? cause.message : "Pairing failed.");
    } finally {
      setBusy(false);
    }
  }

  async function chooseWorkspace(id: string) {
    if (!token) return;
    setWorkspace(id);
    setTabs([]);
    setActivePath("");
    setPatchDialogOpen(false);
    setCollapsedFolders(new Set());
    setBusy(true);
    setError("");
    try {
      setFiles(await listWorkspaceFiles(token, id));
    } catch (cause) {
      setFiles([]);
      setError(cause instanceof Error ? cause.message : "Folder listing failed.");
    } finally {
      setBusy(false);
    }
  }

  async function chooseFile(file: CompanionFile) {
    if (!token || !workspace) return;
    const existing = tabs.find((tab) => tab.path === file.path);
    if (existing) {
      setActivePath(file.path);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const content = await readWorkspaceFile(token, workspace, file.path);
      setTabs((current) => [...current, { path: file.path, content }]);
      setActivePath(file.path);
      setMessage(`Opened ${file.path} in read-only mode.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "File read failed.");
    } finally {
      setBusy(false);
    }
  }

  function openPatchPreview() {
    if (!activeTab) return;
    setPatchDraft(activeTab.content);
    setPatchDiff(null);
    setPatchPreviewError("");
    setPatchDialogOpen(true);
  }

  async function generatePatchPreview() {
    if (!token || !workspace || !activeTab) return;
    setPatchPreviewBusy(true);
    setPatchPreviewError("");
    try {
      const preview = await previewWorkspacePatch(
        token,
        workspace,
        { [activeTab.path]: patchDraft },
        { [activeTab.path]: activeTab.content },
      );
      setPatchDiff(preview.files[0]?.unified_diff ?? "");
      setMessage("Patch diff preview generated. No local files were changed.");
    } catch (cause) {
      setPatchPreviewError(cause instanceof Error ? cause.message : "Patch preview failed.");
    } finally {
      setPatchPreviewBusy(false);
    }
  }

  function closeTab(path: string) {
    const next = tabs.filter((tab) => tab.path !== path);
    setTabs(next);
    if (activePath === path) setActivePath(next.at(-1)?.path ?? "");
  }

  async function disconnect() {
    if (token) {
      try {
        await disconnectFromCompanion(token);
      } catch {
        // The companion may already have been stopped.
      }
    }
    setToken(null);
    setConnected(false);
    setWorkspaces([]);
    setWorkspace("");
    setFiles([]);
    setFileQuery("");
    setCollapsedFolders(new Set());
    setTabs([]);
    setActivePath("");
    setPatchDialogOpen(false);
    setPatchDiff(null);
    setMessage("Disconnected. The in-memory local session was cleared.");
  }

  function toggleFolder(path: string) {
    setCollapsedFolders((current) => {
      const next = new Set(current);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  function handleTreeKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>, node: WorkspaceTreeNode) {
    const root = event.currentTarget.closest('[role="tree"]');
    if (!root) return;
    const items = Array.from(root.querySelectorAll<HTMLButtonElement>('[role="treeitem"]'));
    const index = items.indexOf(event.currentTarget);
    const focus = (item?: HTMLButtonElement) => {
      if (item) {
        event.preventDefault();
        item.focus();
      }
    };
    if (event.key === "ArrowDown") focus(items[index + 1]);
    else if (event.key === "ArrowUp") focus(items[index - 1]);
    else if (event.key === "Home") focus(items[0]);
    else if (event.key === "End") focus(items.at(-1));
    else if (event.key === "ArrowRight" && node.kind === "directory") {
      const collapsed = fileQuery.trim().length === 0 && collapsedFolders.has(node.path);
      if (collapsed) {
        event.preventDefault();
        toggleFolder(node.path);
      } else {
        focus(items.slice(index + 1).find((item) => item.dataset.treePath?.startsWith(node.path + "/")));
      }
    } else if (event.key === "ArrowLeft") {
      if (node.kind === "directory" && !collapsedFolders.has(node.path) && fileQuery.trim().length === 0) {
        event.preventDefault();
        toggleFolder(node.path);
      } else {
        const parentPath = node.path.split("/").slice(0, -1).join("/");
        focus(items.find((item) => item.dataset.treePath === parentPath));
      }
    }
  }

  function renderTree(nodes: WorkspaceTreeNode[], depth = 0): ReactNode[] {
    return nodes.map((node) => {
      if (node.kind === "directory") {
        const collapsed = fileQuery.trim().length === 0 && collapsedFolders.has(node.path);
        return (
          <div key={node.path}>
            <button
              role="treeitem"
              aria-level={depth + 1}
              data-tree-path={node.path}
              onKeyDown={(event) => handleTreeKeyDown(event, node)}
              className="file-row folder-row"
              style={{ paddingLeft: `${7 + depth * 12}px` }}
              aria-expanded={!collapsed}
              onClick={() => toggleFolder(node.path)}
            >
              <span className="file-glyph">{collapsed ? "▸" : "▾"}</span>
              <span className="file-name">{node.name}</span>
            </button>
            {!collapsed && <div role="group">{renderTree(node.children, depth + 1)}</div>}
          </div>
        );
      }
      return (
        <button
          key={node.path}
          role="treeitem"
          aria-level={depth + 1}
          aria-selected={activePath === node.path}
          data-tree-path={node.path}
          onKeyDown={(event) => handleTreeKeyDown(event, node)}
          className={activePath === node.path ? "file-row active" : "file-row"}
          style={{ paddingLeft: `${7 + depth * 12}px` }}
          onClick={() => node.file && void chooseFile(node.file)}
        >
          <span className="file-glyph">▧</span>
          <span className="file-name">{node.name}</span>
          <small>{formatBytes(node.file?.size ?? 0)}</small>
        </button>
      );
    });
  }

  function updateChatSide(side: ChatPanelSide) {
    setChatSide(side);
    writeChatPanelSide(side);
  }

  const chatPanel = (
    <NexusChatPanel
      onClose={() => setChatOpen(false)}
      isOpen={chatOpen}
      activeFile={activeTab ? { path: activeTab.path, content: activeTab.content } : null}
      workspaceContext={token && workspace ? { accessToken: token, workspaceId: workspace, files } : null}
    />
  );

  return (
    <main className="ide-shell">
      <header className="ide-titlebar">
        <div className="brand-lockup"><div className="brand-mark">O</div><div><b>ODEI STUDIO</b><small>Development workspace</small></div></div>
        <div className="titlebar-project"><span className="status-dot" />{workspaceName}</div>
        <div className="titlebar-actions">
          <button className={chatOpen ? "toolbar-button selected" : "toolbar-button"} onClick={() => setChatOpen((open) => !open)}>NEXUS <kbd>⌘ / Ctrl + I</kbd></button>
          <button className="toolbar-button" onClick={() => setSettingsOpen(true)} aria-label="Open settings">⚙ Settings</button>
          {token && <button className="toolbar-button" onClick={() => void disconnect()}>Disconnect</button>}
        </div>
      </header>

      <div className="ide-menubar">
        <span>File</span><span>Edit</span><span>Selection</span><span>View</span><span>Go</span><span>Run</span><span>Terminal</span><span>Help</span>
        <span className="menubar-spacer" />
        <span className="access-pill">LOCAL · READ ONLY</span>
      </div>

      {!token && (
        <section className="welcome-strip">
          <div>
            <span className="eyebrow">LOCAL DEVELOPMENT ENVIRONMENT</span>
            <h1>Open your project workspace</h1>
            <p>Connect to the loopback-only companion, pair once, and browse folders you explicitly select on your computer.</p>
          </div>
          <div className="connect-actions">
            {!connected && <button className="primary-button" disabled={busy} onClick={() => void connect()}>{busy ? "Connecting…" : "Connect local companion"}</button>}
            {connected && <><label htmlFor="pairing-code">One-time pairing code</label><input id="pairing-code" type="password" autoComplete="off" value={code} onChange={(event) => setCode(event.target.value)} placeholder="Code from companion console" /><button className="primary-button" disabled={busy} onClick={() => void pair()}>Pair device</button></>}
          </div>
        </section>
      )}

      <div className="connection-status" role="status" aria-live="polite">{busy ? "Working…" : message}{error && <span className="inline-error">{error}</span>}</div>

      <div className={`workbench ${chatOpen ? `chat-${chatSide}` : "chat-closed"}`}>
        <nav className="activity-rail" aria-label="Activity bar">
          <button className="rail-button active" title="Explorer">▤</button>
          <button className="rail-button" title="Search (not connected)" disabled>⌕</button>
          <button className="rail-button" title="Source control (not connected)" disabled>⑂</button>
          <button className="rail-button" title="Agents window (not connected)" disabled>✧</button>
          <span className="rail-spacer" />
          <button className="rail-button" title="Settings" onClick={() => setSettingsOpen(true)}>⚙</button>
        </nav>

        <aside className="explorer-pane">
          <div className="pane-heading"><strong>EXPLORER</strong><span>{visibleFiles.length}{fileQuery.trim() ? ` / ${files.length}` : ""}</span></div>
          {!token && <div className="pane-empty">Connect the companion to see your selected folders.</div>}
          {token && <>
            <label className="field-label" htmlFor="workspace-select">WORKSPACE</label>
            <select id="workspace-select" value={workspace} onChange={(event) => void chooseWorkspace(event.target.value)}>
              <option value="">Choose a folder…</option>
              {workspaces.map((item) => <option key={item.workspace_id} value={item.workspace_id}>{item.name}</option>)}
            </select>
            <label className="field-label" htmlFor="file-filter">FILTER FILES</label>
            <input id="file-filter" className="file-filter" type="search" value={fileQuery} onChange={(event) => setFileQuery(event.target.value)} placeholder="Search selected file paths…" autoComplete="off" />
            <div className="file-list" role="tree" aria-label="Workspace files">
              {renderTree(workspaceTree)}
              {visibleFiles.length === 0 && <div className="pane-empty">{files.length === 0 ? "No files in this selected workspace." : "No file paths match this filter."}</div>}
            </div>
          </>}
        </aside>

        <section className="editor-column">
          <div className="editor-actionbar">
            {token && activeTab && <button className="patch-preview-trigger" onClick={openPatchPreview}>Preview patch</button>}
          </div>
          <div className="editor-tabs" role="tablist" aria-label="Open files">
            {tabs.map((tab) => <div key={tab.path} className={activePath === tab.path ? "editor-tab active" : "editor-tab"}>
              <button role="tab" aria-selected={activePath === tab.path} onClick={() => setActivePath(tab.path)}>{tab.path.split("/").pop()}</button>
              <button className="tab-close" aria-label={`Close ${tab.path}`} onClick={() => closeTab(tab.path)}>×</button>
            </div>)}
            {tabs.length === 0 && <span className="no-tabs">No file open</span>}
          </div>
          <div className="editor-surface">
            {activeTab ? <MonacoEditor
              height="100%"
              path={activeTab.path}
              language={languageForPath(activeTab.path)}
              value={activeTab.content}
              theme="vs-dark"
              options={{
                readOnly: true,
                minimap: { enabled: false },
                fontSize: 13,
                lineHeight: 21,
                wordWrap: "on",
                scrollBeyondLastLine: false,
                automaticLayout: true,
                renderLineHighlight: "line",
                contextmenu: false,
                domReadOnly: true,
              }}
            /> : <div className="editor-welcome"><div className="editor-logo">O</div><h2>ODEI NEXUS Workspace</h2><p>Select a file from Explorer to inspect it in Monaco.</p><div className="shortcut-hint"><kbd>⌘ / Ctrl + I</kbd> Open NEXUS chat</div></div>}
          </div>
          <section className="bottom-panel">
            <div className="bottom-tabs">
              <button className={bottomPanel === "problems" ? "active" : ""} onClick={() => setBottomPanel("problems")}>PROBLEMS</button>
              <button className={bottomPanel === "output" ? "active" : ""} onClick={() => setBottomPanel("output")}>OUTPUT</button>
              <button className={bottomPanel === "terminal" ? "active" : ""} onClick={() => setBottomPanel("terminal")}>TERMINAL</button>
            </div>
            <div className="bottom-content">
              {bottomPanel === "problems" && "Diagnostics are not connected (no language server)."}
              {bottomPanel === "output" && (error || message)}
              {bottomPanel === "terminal" && "Terminal execution is disabled. Commands will not run in the browser; an isolated execution service is still required."}
            </div>
          </section>
          <footer className="statusbar"><span>{token ? "Companion connected" : "No local workspace"}</span><span>{activeTab ? languageForPath(activeTab.path) : "Plain Text"}</span><span>UTF-8</span><span>READ ONLY</span></footer>
        </section>

        {chatPanel}
      </div>

      {patchDialogOpen && activeTab && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPatchDialogOpen(false); }}>
        <section className="settings-dialog patch-dialog" role="dialog" aria-modal="true" aria-labelledby="patch-preview-title">
          <div className="pane-heading">
            <strong id="patch-preview-title">PREVIEW PATCH · {activeTab.path}</strong>
            <button className="icon-button" onClick={() => setPatchDialogOpen(false)} aria-label="Close patch preview">×</button>
          </div>
          <p>Edit the proposed replacement below, then generate a live diff against the selected workspace file.</p>
          <label className="field-label" htmlFor="patch-draft">PROPOSED FILE CONTENT</label>
          <textarea
            id="patch-draft"
            className="patch-draft"
            value={patchDraft}
            onChange={(event) => { setPatchDraft(event.target.value); setPatchDiff(null); }}
            maxLength={1_000_000}
            rows={12}
            spellCheck={false}
          />
          <div className="patch-preview-actions">
            <button className="primary-button" disabled={patchPreviewBusy} onClick={() => void generatePatchPreview()}>
              {patchPreviewBusy ? "Generating…" : "Generate diff"}
            </button>
            <button className="toolbar-button" onClick={() => setPatchDialogOpen(false)}>Close</button>
          </div>
          {patchPreviewError && <p className="inline-error patch-preview-error" role="alert">{patchPreviewError}</p>}
          {patchDiff !== null && <div className="patch-diff-wrap">
            <strong>UNIFIED DIFF · PREVIEW ONLY</strong>
            <pre className="patch-diff">{patchDiff || "No textual differences."}</pre>
          </div>}
          <p className="settings-note">Preview only. No files are written, deleted or approved. Applying changes is not enabled.</p>
        </section>
      </div>}

      {settingsOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSettingsOpen(false); }}>
        <section className="settings-dialog" role="dialog" aria-modal="true" aria-labelledby="settings-title">
          <div className="pane-heading"><strong id="settings-title">WORKSPACE SETTINGS</strong><button className="icon-button" onClick={() => setSettingsOpen(false)} aria-label="Close settings">×</button></div>
          <h2>NEXUS chat panel</h2>
          <p>Choose which side of the editor the AI chat panel opens on when you press Command+I (macOS) or Ctrl+I (Windows/Linux).</p>
          <fieldset className="side-options"><legend>Open chat panel on</legend>
            <label><input type="radio" name="chat-side" value="left" checked={chatSide === "left"} onChange={() => updateChatSide("left")} /> Left side</label>
            <label><input type="radio" name="chat-side" value="right" checked={chatSide === "right"} onChange={() => updateChatSide("right")} /> Right side</label>
          </fieldset>
          <p className="settings-note">Preference is saved in this browser. Default: Right.</p>
          <button className="primary-button" onClick={() => setSettingsOpen(false)}>Done</button>
        </section>
      </div>}
    </main>
  );
}
