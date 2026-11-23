import { useState, type FormEvent } from "react";
import "./studio-home.css";

interface Props {
  onOpenWorkspace: () => void;
  onStartChat: (prompt: string) => void;
  onCustomize: () => void;
  workspaceName: string;
  companionConnected: boolean;
}

const suggestions = [
  { icon: "△", title: "Deploy my prototype", detail: "Prepare a project for a shareable live link", action: "workspace" },
  { icon: "⌁", title: "Review my database", detail: "Inspect schema, indexes and access rules", action: "chat" },
  { icon: "☷", title: "Start with a plan", detail: "Turn an idea into a clear implementation plan", action: "plan" },
  { icon: "⚙", title: "Debug an issue", detail: "Investigate a problem and trace its root cause", action: "chat" },
] as const;

export default function ODEIStudioHome({
  onOpenWorkspace, onStartChat, onCustomize, workspaceName, companionConnected,
}: Props) {
  const [prompt, setPrompt] = useState("");
  const [activeSection, setActiveSection] = useState("New Chat");
  const [minimized, setMinimized] = useState(false);
  const [maximized, setMaximized] = useState(false);
  const [closed, setClosed] = useState(false);
  const [showApps, setShowApps] = useState(false);
  const [overflowOpen, setOverflowOpen] = useState(false);
  const [activeMenu, setActiveMenu] = useState<string | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);

  function openIndependentIDE() {
    const url = new URL(window.location.href);
    url.searchParams.set("window", "ide");
    const ideWindow = window.open(url.toString(), "odei-ide-window", "popup=yes,width=1440,height=900,resizable=yes,scrollbars=yes");
    if (ideWindow) ideWindow.focus();
  }

  async function toggleMaximize() {
    const next = !maximized;
    setMaximized(next);
    try {
      if (next && !document.fullscreenElement) await document.documentElement.requestFullscreen();
      else if (!next && document.fullscreenElement) await document.exitFullscreen();
    } catch {
      // Keep the in-app expanded layout when fullscreen is unavailable.
    }
  }

  if (closed) return <section className="studio-home studio-home-exited" aria-label="ODEI Studio closed"><div className="studio-exit-card"><span className="studio-home-mark">O</span><h1>ODEI Studio is closed</h1><p>The ODEI workspace view is closed. Your browser window remains under browser control.</p><button className="studio-reopen-button" onClick={() => { setClosed(false); setMinimized(false); }}>Reopen ODEI Studio</button></div></section>;

  function runMenuAction(action: string) {\n    setActiveMenu(null);\n    switch (action) {\n      case "new-chat": onStartChat(""); break;\n      case "open-workspace": onOpenWorkspace(); break;\n      case "close": setClosed(true); break;\n      case "focus-prompt": document.getElementById("studio-home-prompt")?.focus(); break;\n      case "select-prompt": { const field = document.getElementById("studio-home-prompt") as HTMLTextAreaElement | null; field?.focus(); field?.select(); break; }\n      case "clear-prompt": setPrompt(""); document.getElementById("studio-home-prompt")?.focus(); break;\n      case "customize": onCustomize(); break;\n      case "open-ide": openIndependentIDE(); break;\n      case "show-apps": setShowApps(true); break;\n      case "start-plan": onStartChat(prompt.trim() || "Help me plan a new project. Clarify its goal, constraints, architecture and first deliverable."); break;\n      case "help": setHelpOpen(true); break;\n    }\n  }\n\n  const menuItems: Record<string, Array<{ label: string; action: string; shortcut?: string }>> = {\n    File: [{label:"New Chat",action:"new-chat",shortcut:"Ctrl+N"},{label:"Open Workspace",action:"open-workspace",shortcut:"Ctrl+O"},{label:"Close ODEI Studio",action:"close"}],\n    Edit: [{label:"Focus Prompt",action:"focus-prompt"},{label:"Select Prompt Text",action:"select-prompt",shortcut:"Ctrl+A"},{label:"Clear Prompt",action:"clear-prompt"},{label:"Customize",action:"customize"}],\n    Selection: [{label:"Select Prompt Text",action:"select-prompt",shortcut:"Ctrl+A"},{label:"Clear Prompt",action:"clear-prompt"}],\n    View: [{label:"Open IDE in New Window",action:"open-ide"},{label:"Show Apps",action:"show-apps"}],\n    Go: [{label:"Open Workspace",action:"open-workspace"},{label:"Focus Prompt",action:"focus-prompt"}],\n    Run: [{label:"Start with a Plan",action:"start-plan"}],\n    Terminal: [{label:"Open IDE Workspace",action:"open-workspace"}],\n    Help: [{label:"Keyboard Shortcuts",action:"help"}],\n  };\n\n  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onStartChat(prompt.trim());
  }

  function chooseSuggestion(action: (typeof suggestions)[number]["action"], title: string) {
    if (action === "workspace") onOpenWorkspace();
    else onStartChat(action === "plan" ? prompt.trim() || "Help me plan a new project. Start by clarifying the goal, constraints, architecture and first deliverable." : prompt.trim() || title);
  }

  return (
    <section className="studio-home" aria-label="ODEI Studio Window">
      <header className="studio-home-menubar">
        <div className="studio-home-brand"><span className="studio-home-mark">O</span><strong>ODEI STUDIO</strong></div>
        <nav aria-label="Application menu">{Object.keys(menuItems).map((menu) => <button key={menu} type="button" className={activeMenu === menu ? "studio-menubar-item active" : "studio-menubar-item"} aria-haspopup="menu" aria-expanded={activeMenu === menu} onClick={() => { setActiveMenu((current) => current === menu ? null : menu); setShowApps(false); setOverflowOpen(false); }}>{menu}</button>)}</nav>\n        {activeMenu && <div className="studio-menubar-popover" role="menu" aria-label={`${activeMenu} menu`}>{menuItems[activeMenu].map((item) => <button key={item.label} type="button" role="menuitem" onClick={() => runMenuAction(item.action)}><span>{item.label}</span>{item.shortcut && <kbd>{item.shortcut}</kbd>}</button>)}</div>}
        <span className="studio-home-window-label">ODEI Studio Window</span>
        <div className="studio-home-tools">
          <button type="button" className="studio-ide-label" aria-label="Open IDE in independent window" title="Open IDE in independent window" onClick={openIndependentIDE}>IDE</button>
          <div className="studio-menu-anchor">
            <button type="button" className="studio-topbar-icon" aria-label="Show apps" title="Show apps" aria-expanded={showApps} onClick={() => { setShowApps((open) => !open); setOverflowOpen(false); }}>▦</button>
            {showApps && <div className="studio-topbar-popover studio-app-launcher" role="dialog" aria-label="Apps">
              <div className="studio-popover-heading">Your apps</div>
              <button type="button" className="studio-app-tile" onClick={() => { setShowApps(false); onOpenWorkspace(); }}><span>▱</span><strong>IDE Workspace</strong></button>
              <button type="button" className="studio-app-tile" onClick={() => { setShowApps(false); onStartChat(""); }}><span>✧</span><strong>NEXUS</strong></button>
              <button type="button" className="studio-app-tile" onClick={() => { setShowApps(false); onOpenWorkspace(); }}><span>▦</span><strong>Projects</strong></button>
              <button type="button" className="studio-app-tile" onClick={() => { setShowApps(false); onCustomize(); }}><span>⚙</span><strong>Settings</strong></button>
            </div>}
          </div>
          <div className="studio-menu-anchor">
            <button type="button" className="studio-topbar-icon studio-more-button" aria-label="More options" title="More options" aria-expanded={overflowOpen} onClick={() => { setOverflowOpen((open) => !open); setShowApps(false); }}>⋯</button>
            {overflowOpen && <div className="studio-topbar-popover studio-overflow-menu" role="menu" aria-label="IDE options">
              <button type="button" role="menuitem" onClick={() => { setOverflowOpen(false); onStartChat(""); }}>New chat</button>
              <button type="button" role="menuitem" onClick={() => { setOverflowOpen(false); onOpenWorkspace(); }}>Open workspace</button>
              <button type="button" role="menuitem" onClick={() => { setOverflowOpen(false); onCustomize(); }}>Customize</button>
              <div className="studio-popover-divider" />
              <button type="button" role="menuitem" onClick={() => { setOverflowOpen(false); setMinimized(true); }}>Minimize window</button>
              <button type="button" role="menuitem" onClick={() => { setOverflowOpen(false); void toggleMaximize(); }}>{maximized ? "Restore down" : "Maximize window"}</button>
              <button type="button" role="menuitem" className="studio-menu-danger" onClick={() => { setOverflowOpen(false); setClosed(true); }}>Close ODEI Studio</button>
            </div>}
          </div>
        </div>
        <div className="studio-window-controls" role="group" aria-label="ODEI Studio window controls">
          <button type="button" className="studio-window-control" aria-label="Minimize ODEI Studio" title="Minimize" onClick={() => setMinimized(true)}>—</button>
          <button type="button" className="studio-window-control" aria-label={maximized ? "Restore ODEI Studio" : "Maximize ODEI Studio"} title={maximized ? "Restore down" : "Maximize"} onClick={() => void toggleMaximize()}>{maximized ? "❐" : "□"}</button>
          <button type="button" className="studio-window-control studio-window-close" aria-label="Close ODEI Studio" title="Close" onClick={() => { if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined); setClosed(true); }}>×</button>
        </div>
      </header>

      {helpOpen && <div className="studio-help-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setHelpOpen(false); }}><section className="studio-help-dialog" role="dialog" aria-modal="true" aria-labelledby="studio-help-title"><div className="studio-help-heading"><strong id="studio-help-title">KEYBOARD SHORTCUTS</strong><button type="button" aria-label="Close keyboard shortcuts" onClick={() => setHelpOpen(false)}>×</button></div><p><kbd>Ctrl / ⌘ + N</kbd> New Chat</p><p><kbd>Ctrl / ⌘ + O</kbd> Open Workspace</p><p><kbd>Ctrl / ⌘ + A</kbd> Select prompt text</p><p><kbd>Ctrl / ⌘ + I</kbd> Toggle NEXUS in the IDE workspace</p><button type="button" onClick={() => setHelpOpen(false)}>Done</button></section></div>}\n      {minimized ? <div className="studio-minimized-view"><span className="studio-home-mark">O</span><strong>ODEI Studio is minimized</strong><button type="button" onClick={() => setMinimized(false)}>Restore ODEI Studio</button></div> : <div className="studio-home-layout">
        <aside className="studio-home-sidebar">
          <div className="studio-home-nav" aria-label="Primary navigation">
            <button className={activeSection === "New Chat" ? "studio-nav-item active" : "studio-nav-item"} onClick={() => { setActiveSection("New Chat"); onStartChat(""); }}>
              <span>✧</span>New Chat
            </button>
            <button className="studio-nav-item disabled" disabled title="Automations are not connected yet"><span>◷</span>Automations <small>Coming soon</small></button>
            <button className="studio-nav-item" onClick={onCustomize}><span>☷</span>Customize</button>
          </div>

          <section className="studio-sidebar-section">
            <div className="studio-sidebar-heading"><span>Projects</span><button title="Open workspace" aria-label="Open workspace" onClick={onOpenWorkspace}>＋</button></div>
            <button className="studio-project-row" onClick={onOpenWorkspace}>
              <span className="studio-project-icon">▱</span>
              <span><strong>{workspaceName || "Open a workspace"}</strong><small>{companionConnected ? "Local companion connected" : "No project open yet"}</small></span>
            </button>
          </section>

          <section className="studio-sidebar-section studio-repositories">
            <div className="studio-sidebar-heading"><span>Repositories</span><span className="studio-muted-count">LOCAL</span></div>
            <div className="studio-empty-repository">
              <span className="studio-folder-icon">▰</span>
              <p>Connect your local companion to browse repositories and folders you choose.</p>
              <button onClick={onOpenWorkspace}>Open workspace</button>
            </div>
          </section>

          <div className="studio-getting-started">
            <div className="studio-getting-heading"><strong>Getting Started</strong><span>0/3</span></div>
            <div className="studio-progress"><span /></div>
            <ol>
              <li><span>1</span>Open a workspace</li>
              <li><span>2</span>Connect your tools</li>
              <li><span>3</span>Start building with NEXUS</li>
            </ol>
            <button onClick={onOpenWorkspace}>Open local workspace</button>
          </div>
          <footer className="studio-sidebar-footer"><span className="studio-avatar">O</span><span><strong>ODEI Studio</strong><small>Personal workspace</small></span><button onClick={onCustomize} aria-label="Settings">⚙</button></footer>
        </aside>

        <section className="studio-home-main">
          <div className="studio-home-main-top"><span className="studio-context-chip"><span className="studio-context-dot" />{workspaceName || "No project selected"} <span>⌄</span></span><span className="studio-context-chip">▣ This PC <span>⌄</span></span></div>
          <div className="studio-home-content">
            <div className="studio-hero-mark">O</div>
            <span className="studio-eyebrow">YOUR AI-NATIVE DEVELOPMENT WORKSPACE</span>
            <h1>What are we building today?</h1>
            <p className="studio-hero-copy">Plan, build, debug and ship software with ODEI NEXUS by your side.</p>

            <form className="studio-prompt-card" onSubmit={submit}>
              <label className="studio-sr-only" htmlFor="studio-home-prompt">Describe what you want to build</label>
              <textarea id="studio-home-prompt" rows={3} maxLength={8000} value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Plan, build, / for skills, @ for context" />
              <div className="studio-prompt-toolbar">
                <button type="button" className="studio-add-context" title="Open workspace context" onClick={onOpenWorkspace}>＋</button>
                <span className="studio-prompt-hint">NEXUS · Project-aware assistance</span>
                <span className="studio-model-indicator"><i />NEXUS</span>
                <button className="studio-send-button" type="submit" disabled={!prompt.trim()} aria-label="Start with NEXUS">↑</button>
              </div>
            </form>

            <div className="studio-quick-actions"><button onClick={() => onStartChat(prompt.trim() || "Help me plan a new project. Start by clarifying the goal, constraints, architecture and first deliverable.")}>Start with a plan <kbd>↵</kbd></button><button onClick={onOpenWorkspace}>Open workspace</button></div>

            <div className="studio-suggestions" aria-label="Suggested starting points">
              {suggestions.map((item) => (
                <button key={item.title} className="studio-suggestion" onClick={() => chooseSuggestion(item.action, item.title)}>
                  <span className="studio-suggestion-icon">{item.icon}</span><strong>{item.title}</strong><small>{item.detail}</small><span className="studio-suggestion-arrow">↗</span>
                </button>
              ))}
            </div>
            <p className="studio-home-footnote">Tip: use <kbd>/ask</kbd> in the workspace to research your codebase before making changes.</p>
          </div>
          <div className="studio-home-status"><span>{companionConnected ? "Local companion connected" : "Local workspace not connected"}</span><span>ODEI Studio Window</span></div>
        </section>
      </div>}
    </section>
  );
}
