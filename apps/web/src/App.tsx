import { useEffect, useMemo, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import MonacoEditor from "@monaco-editor/react";
import NexusChatPanel from "./NexusChatPanel";
import ODEIStudioHome from "./ODEIStudioHome";
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
  const [homeOpen, setHomeOpen] = useState(() => {
    if (new URLSearchParams(window.location.search).get("window") === "ide") return false;
    try {
      const callback = new URL(import.meta.env.VITE_ODID_REDIRECT_URI);
      const isAuthCallback = window.location.origin === callback.origin
        && window.location.pathname === callback.pathname
        && Boolean(window.location.search);
      return !isAuthCallback;
    } catch {
      return true;
    }
  });
  const [initialPrompt, setInitialPrompt] = useState("");
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
    if (new URLSearchParams(window.location.search).get("window") === "ide") return true;
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
  const [activeWorkbenchMenu, setActiveWorkbenchMenu] = useState<string | null>(null);
  const isIDEWindow = new URLSearchParams(window.location.search).get("window") === "ide";
  const [activeEditorView, setActiveEditorView] = useState<"editor" | "browser">(() => isIDEWindow ? "browser" : "editor");
  const [browserUrl, setBrowserUrl] = useState("http://127.0.0.1:3003");
  const [browserDraft, setBrowserDraft] = useState("http://127.0.0.1:3003");
  const [browserHistory, setBrowserHistory] = useState<string[]>(["http://127.0.0.1:3003"]);
  const [browserHistoryIndex, setBrowserHistoryIndex] = useState(0);
  const [browserReloadKey, setBrowserReloadKey] = useState(0);
  const [browserMenuOpen, setBrowserMenuOpen] = useState(false);
  const [browserFavorite, setBrowserFavorite] = useState(false);
  const [browserToolsOpen, setBrowserToolsOpen] = useState(false);
  const [ideMinimized, setIdeMinimized] = useState(false);
  const [ideMaximized, setIdeMaximized] = useState(false);

  const [patchDialogOpen, setPatchDialogOpen] = useState(false);
  const [patchDraft, setPatchDraft] = useState("");
  const [patchDiff, setPatchDiff] = useState<string | null>(null);
  const [patchPreviewBusy, setPatchPreviewBusy] = useState(false);
  const [patchPreviewError, setPatchPreviewError] = useState("");

  // Keep modal dialogs keyboard-operable: move focus in, contain Tab navigation,
  // close on Escape, and restore focus to the control that opened the dialog.
  useEffect(() => {
    if (!patchDialogOpen && !settingsOpen) return;
    const dialog = document.querySelector<HTMLElement>('[role="dialog"][aria-modal="true"]');
    if (!dialog) return;
    const activeDialog = dialog;
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const focusable = () => Array.from(activeDialog.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    )).filter((element) => element.getAttribute("aria-hidden") !== "true");
    focusable()[0]?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        if (patchDialogOpen) setPatchDialogOpen(false);
        else setSettingsOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (items.length === 0) {
        event.preventDefault();
        activeDialog.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && (document.activeElement === first || !activeDialog.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !activeDialog.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [patchDialogOpen, settingsOpen]);

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
        setHomeOpen(false);
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
      setActiveEditorView("editor");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const content = await readWorkspaceFile(token, workspace, file.path);
      setTabs((current) => [...current, { path: file.path, content }]);
      setActivePath(file.path);
      setActiveEditorView("editor");
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

  function navigateBrowser(nextValue = browserDraft) {
    const candidate = nextValue.trim();
    if (!candidate) return;
    let parsed: URL;
    try { parsed = new URL(/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(candidate) ? candidate : `http://${candidate}`); }
    catch { setMessage("Enter a valid web address."); return; }
    if (!["http:", "https:"].includes(parsed.protocol)) { setMessage("Only HTTP and HTTPS browser navigation is allowed."); return; }
    const next = parsed.toString();
    setBrowserUrl(next); setBrowserDraft(next);
    setBrowserHistory((items) => [...items.slice(0, browserHistoryIndex + 1), next]);
    setBrowserHistoryIndex((index) => index + 1);
    setBrowserReloadKey((key) => key + 1);
    setActiveEditorView("browser");
  }
  function moveBrowserHistory(delta: number) {
    const nextIndex = browserHistoryIndex + delta;
    if (nextIndex < 0 || nextIndex >= browserHistory.length) return;
    setBrowserHistoryIndex(nextIndex);
    setBrowserUrl(browserHistory[nextIndex]);
    setBrowserDraft(browserHistory[nextIndex]);
    setBrowserReloadKey((key) => key + 1);
  }
  async function copyBrowserUrl() {
    try { await navigator.clipboard.writeText(browserUrl); setMessage("Browser address copied."); }
    catch { setMessage("Clipboard access is unavailable in this browser context."); }
  }

  function runWorkbenchCommand(command: string) {
    setActiveWorkbenchMenu(null);
    switch (command) {
      case "open-workspace": if (!token) { setMessage("Connect the local companion, then select a folder you explicitly choose."); document.querySelector<HTMLButtonElement>(".connect-actions .primary-button")?.click(); document.getElementById("pairing-code")?.focus(); } else { document.getElementById("workspace-select")?.focus(); } break;
      case "close-editor": if (activePath) closeTab(activePath); else setMessage("There is no open editor tab to close."); break;
      case "search": if (token) document.getElementById("file-filter")?.focus(); else setMessage("Connect the local companion and select a workspace before searching its files."); break;
      case "source-control": setMessage("Source Control is not connected. Connect a Git provider before using repository operations."); break;
      case "explorer": document.querySelector<HTMLElement>(".explorer-pane")?.focus(); setMessage("Explorer is active. Connect the companion to browse selected folders."); break;
      case "agents": setChatOpen(true); break;
      case "settings": setSettingsOpen(true); break;
      case "terminal": setBottomPanel("terminal"); break;
      case "output": setBottomPanel("output"); break;
      case "problems": setBottomPanel("problems"); break;
      case "quick-open": document.getElementById("file-filter")?.focus(); break;
      case "run": setMessage("Run is unavailable until a trusted, isolated execution service is configured."); setBottomPanel("output"); break;
      case "home": setHomeOpen(true); break;
      case "help": setMessage("Shortcuts: Ctrl/⌘+I toggles NEXUS; Ctrl/⌘+S reports read-only status. Use the Explorer filter to find files."); break;
    }
  }
  const workbenchMenus: Record<string, Array<{label:string; command:string}>> = {
    File:[{label:"Open Workspace",command:"open-workspace"},{label:"Close Active Editor",command:"close-editor"},{label:"Home",command:"home"}],
    Edit:[{label:"Find in Workspace",command:"search"},{label:"Settings",command:"settings"}],
    Selection:[{label:"Focus File Filter",command:"quick-open"}],
    View:[{label:"Explorer",command:"explorer"},{label:"NEXUS Chat",command:"agents"},{label:"Output",command:"output"},{label:"Problems",command:"problems"},{label:"Terminal",command:"terminal"}],
    Go:[{label:"Quick Open",command:"quick-open"}],
    Run:[{label:"Run Task",command:"run"}],
    Terminal:[{label:"Show Terminal Panel",command:"terminal"}],
    Help:[{label:"Keyboard Shortcuts",command:"help"}],
  };

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
      initialPrompt={initialPrompt}
    />
  );

  return (
    <main className={isIDEWindow ? `ide-shell ide-reference${ideMaximized ? " ide-maximized" : ""}` : "ide-shell"}>
      {homeOpen ? <ODEIStudioHome
        onOpenWorkspace={() => setHomeOpen(false)}
        onStartChat={(prompt) => { setInitialPrompt(prompt); setHomeOpen(false); setChatOpen(true); }}
        onCustomize={() => { setHomeOpen(false); setSettingsOpen(true); }}
        workspaceName={workspaceName === "No folder open" ? "" : workspaceName}
        companionConnected={Boolean(token)}
      /> : <>
      <header className="ide-titlebar">
        <div className="brand-lockup"><div className="brand-mark">◆</div><div><b>{isIDEWindow ? "OIPTECH Core" : "ODEI STUDIO"}</b><small>{isIDEWindow ? "Workspace" : "Development workspace"}</small></div></div>
        <div className="titlebar-project"><span className="status-dot" />{workspaceName}</div>
        <div className="titlebar-actions">
          <button className="toolbar-button" onClick={() => setHomeOpen(true)} aria-label="Open ODEI Studio Window">⌂ Home</button>
          <button className={chatOpen ? "toolbar-button selected" : "toolbar-button"} onClick={() => setChatOpen((open) => !open)}>{isIDEWindow ? "Agents Window ↗" : <>NEXUS <kbd>⌘ / Ctrl + I</kbd></>}</button>
          <button className="toolbar-button" onClick={() => setSettingsOpen(true)} aria-label="Open settings">⚙ Settings</button>
          {token && <button className="toolbar-button" onClick={() => void disconnect()}>Disconnect</button>}
          {isIDEWindow && <div className="ide-native-controls" role="group" aria-label="IDE window controls">
            <button type="button" aria-label="Minimize IDE window" title="Minimize" onClick={() => setIdeMinimized(true)}>—</button>
            <button type="button" aria-label={ideMaximized ? "Restore IDE window" : "Maximize IDE window"} title={ideMaximized ? "Restore" : "Maximize"} onClick={() => { const next = !ideMaximized; setIdeMaximized(next); if (next) void document.documentElement.requestFullscreen?.().catch(() => undefined); else if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined); }}>{ideMaximized ? "❐" : "□"}</button>
            <button type="button" aria-label="Close IDE window" title="Close" onClick={() => { if (window.opener) window.close(); else setHomeOpen(true); }}>×</button>
          </div>}
        </div>
      </header>

      {ideMinimized && isIDEWindow ? <div className="ide-minimized-overlay"><strong>OIPTECH Core is minimized</strong><button type="button" onClick={() => setIdeMinimized(false)}>Restore window</button></div> : null}\n      <div className="ide-menubar">
        <nav className="ide-menu-items" aria-label="Workbench menu">{Object.keys(workbenchMenus).map((menu) => <button type="button" key={menu} aria-haspopup="menu" aria-expanded={activeWorkbenchMenu === menu} onClick={() => setActiveWorkbenchMenu((current) => current === menu ? null : menu)}>{menu}</button>)}</nav>{activeWorkbenchMenu && <div className="ide-menu-popover" role="menu" aria-label={`${activeWorkbenchMenu} menu`}>{workbenchMenus[activeWorkbenchMenu].map((item) => <button type="button" role="menuitem" key={item.label} onClick={() => runWorkbenchCommand(item.command)}>{item.label}</button>)}</div>}
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
          <button className="rail-button active" title="Explorer" aria-label="Explorer" onClick={() => runWorkbenchCommand("explorer")}>▤</button>
          <button className="rail-button" title="Search workspace files" aria-label="Search workspace files" onClick={() => runWorkbenchCommand("search")}>⌕</button>
          <button className="rail-button" title="Source control status" aria-label="Source control status" onClick={() => runWorkbenchCommand("source-control")}>⑂</button>
          <button className="rail-button" title="Open Agents and NEXUS" aria-label="Open Agents and NEXUS" onClick={() => runWorkbenchCommand("agents")}>✧</button>
          <span className="rail-spacer" />
          <button className="rail-button" title="Settings" aria-label="Settings" onClick={() => setSettingsOpen(true)}>⚙</button>
        </nav>

        <aside className="explorer-pane" tabIndex={-1}>
          <div className="pane-heading"><strong>{isIDEWindow ? "OIPTECH CORE" : "EXPLORER"}</strong><div className="explorer-actions"><span>{visibleFiles.length}{fileQuery.trim() ? ` / ${files.length}` : ""}</span><button type="button" aria-label="Search files" title="Search files" onClick={() => { if (token) document.getElementById("file-filter")?.focus(); else setMessage("Connect the local companion and select a workspace before searching files."); }}>⌕</button><button type="button" aria-label="Refresh Explorer" title="Refresh Explorer" onClick={() => { if (token && workspace) void chooseWorkspace(workspace); else setMessage("Connect the local companion to refresh the Explorer."); }}>↻</button><button type="button" aria-label="Collapse all folders" title="Collapse all folders" onClick={() => { const folders = files.filter((file) => file.kind === "directory").map((file) => file.path); setCollapsedFolders(new Set(folders)); setMessage(folders.length ? `Collapsed ${folders.length} Explorer folders.` : "There are no loaded folders to collapse."); }}>⌄</button></div></div>
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
            <button role="tab" aria-selected={activeEditorView === "browser"} className={activeEditorView === "browser" ? "editor-tab browser-tab active" : "editor-tab browser-tab"} onClick={() => setActiveEditorView("browser")}>◎ Browser Tab</button>
            <button type="button" className="editor-tab-action" aria-label="New browser tab" title="New browser tab" onClick={() => { setBrowserDraft("http://127.0.0.1:3003"); navigateBrowser("http://127.0.0.1:3003"); }}>＋</button>
            <button type="button" className="editor-tab-action" aria-label="Browser tab options" title="Browser tab options" aria-expanded={browserMenuOpen} onClick={() => setBrowserMenuOpen((open) => !open)}>⋯</button>
            {browserMenuOpen && <div className="browser-tab-menu" role="menu" aria-label="Browser tab options">
              <button role="menuitem" onClick={() => { setBrowserMenuOpen(false); void copyBrowserUrl(); }}>Copy address</button>
              <button role="menuitem" onClick={() => { setBrowserMenuOpen(false); window.open(browserUrl, "_blank", "noopener,noreferrer"); }}>Open in new tab</button>
              <button role="menuitem" onClick={() => { setBrowserMenuOpen(false); setBrowserFavorite(false); setBrowserDraft("http://127.0.0.1:3003"); navigateBrowser("http://127.0.0.1:3003"); }}>Reset browser</button>
            </div>
          </div>
          <div className="editor-surface">
            {activeEditorView === "browser" ? <section className="embedded-browser" aria-label="Browser Tab">
              <form className="browser-toolbar" onSubmit={(event) => { event.preventDefault(); navigateBrowser(); }}>
                <button type="button" aria-label="Browser back" title="Back" disabled={browserHistoryIndex <= 0} onClick={() => moveBrowserHistory(-1)}>‹</button>
                <button type="button" aria-label="Browser forward" title="Forward" disabled={browserHistoryIndex >= browserHistory.length - 1} onClick={() => moveBrowserHistory(1)}>›</button>
                <button type="button" aria-label="Reload browser" title="Reload" onClick={() => setBrowserReloadKey((key) => key + 1)}>↻</button>
                <button type="button" aria-label={browserFavorite ? "Remove browser favorite" : "Add browser favorite"} title="Favorite" onClick={() => setBrowserFavorite((value) => !value)}>{browserFavorite ? "★" : "☆"}</button>
                <input aria-label="Browser address" value={browserDraft} onChange={(event) => setBrowserDraft(event.target.value)} />
                <button type="submit" aria-label="Navigate browser" title="Go">↵</button>
                <button type="button" aria-label="Open browser in new tab" title="Open in new tab" onClick={() => window.open(browserUrl, "_blank", "noopener,noreferrer")}>↗</button>
                <button type="button" aria-label="Browser developer tools information" title="Developer tools" onClick={() => setBrowserToolsOpen((open) => !open)}>⌘</button>
              </form>
              {browserToolsOpen && <div className="browser-tools-note" role="status">Browser developer tools are provided by the host browser. Press F12 or Ctrl+Shift+I to inspect this tab.</div>}
              <iframe key={browserReloadKey} title="Embedded browser preview" src={browserUrl} className="browser-frame" referrerPolicy="no-referrer" sandbox="allow-forms allow-scripts allow-popups" />
            </section> : activeTab ? <MonacoEditor
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
            /> : <div className="editor-welcome"><div className="editor-logo">O</div><h2>OIPTECH Core</h2><p>Select a file from Explorer or open the Browser Tab.</p><div className="shortcut-hint"><kbd>⌘ / Ctrl + I</kbd> Open NEXUS chat</div></div>}
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
      </>}
    </main>
  );
}
