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

  function submit(event: FormEvent<HTMLFormElement>) {
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
        <nav aria-label="Application menu"><span>File</span><span>Edit</span><span>View</span><span>Window</span><span>Help</span></nav>
        <span className="studio-home-window-label">ODEI Studio Window</span>
      </header>

      <div className="studio-home-layout">
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
      </div>
    </section>
  );
}
