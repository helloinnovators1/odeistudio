import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  beginODIDLogin,
  completeODIDLogin,
  type ODidAccessToken,
  type ODidOAuthConfig,
} from "./odid-auth";
import { listNexusOrganizations, listNexusProjects, type NexusOrganization, type NexusProject } from "./projects";
import { createNexusConversation, deleteNexusConversation, getNexusConversation, listNexusConversations, sendNexusChat, type NexusChatMessage, type NexusConversationSummary } from "./nexus-chat";
import { approveNexusTask, cancelNexusTask, createNexusTask, type NexusTask } from "./nexus-tasks";
import "./nexus-chat-panel.css";

interface Props {
  onClose: () => void;
  isOpen?: boolean;
  activeFile?: { path: string; content: string } | null;
}

interface TranscriptMessage extends NexusChatMessage {
  id: string;
}

function environmentConfig(): { auth: ODidOAuthConfig | null; apiBaseUrl: string; missing: string[] } {
  const env = import.meta.env;
  const issuer = env.VITE_ODID_ISSUER?.trim() ?? "";
  const clientId = env.VITE_ODID_CLIENT_ID?.trim() ?? "";
  const redirectUri = env.VITE_ODID_REDIRECT_URI?.trim() ?? "";
  const resource = env.VITE_ODID_API_RESOURCE?.trim() ?? "";
  const scopes = (env.VITE_ODID_SCOPES ?? "").split(/[ ,]+/).filter(Boolean);
  const apiBaseUrl = env.VITE_ODEI_API_BASE_URL?.trim() ?? "";
  const values: Record<string, string | string[]> = {
    VITE_ODID_ISSUER: issuer,
    VITE_ODID_CLIENT_ID: clientId,
    VITE_ODID_REDIRECT_URI: redirectUri,
    VITE_ODID_API_RESOURCE: resource,
    VITE_ODID_SCOPES: scopes,
    VITE_ODEI_API_BASE_URL: apiBaseUrl,
  };
  const missing = Object.entries(values)
    .filter(([, value]) => Array.isArray(value) ? value.length === 0 : !value)
    .map(([key]) => key);
  const auth = missing.length === 0
    ? { issuer, clientId, redirectUri, resource, scopes }
    : null;
  return { auth, apiBaseUrl, missing };
}

function errorMessage(cause: unknown): string {
  return cause instanceof Error ? cause.message : "NEXUS could not complete the request.";
}

function newMessageId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function NexusChatPanel({ onClose, isOpen = true, activeFile = null }: Props) {
  const config = useMemo(environmentConfig, []);
  const [access, setAccess] = useState<ODidAccessToken | null>(null);
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState("");
  const [organizations, setOrganizations] = useState<NexusOrganization[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const [organizationBusy, setOrganizationBusy] = useState(false);
  const [organizationError, setOrganizationError] = useState("");
  const [projects, setProjects] = useState<NexusProject[]>([]);
  const [projectId, setProjectId] = useState("");
  const [projectBusy, setProjectBusy] = useState(false);
  const [projectError, setProjectError] = useState("");
  const [messages, setMessages] = useState<TranscriptMessage[]>([]);
  const [conversations, setConversations] = useState<NexusConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState("");
  const [conversationBusy, setConversationBusy] = useState(false);
  const [draft, setDraft] = useState("");
  const [consent, setConsent] = useState(false);
  const [attachActiveFile, setAttachActiveFile] = useState(false);
  const [sending, setSending] = useState(false);
  const [chatError, setChatError] = useState("");
  const [taskPlan, setTaskPlan] = useState<NexusTask | null>(null);
  const [taskBusy, setTaskBusy] = useState(false);
  const [taskError, setTaskError] = useState("");
  const [notice, setNotice] = useState("Sign in and select an authorized project to start.");
  const abortRef = useRef<AbortController | null>(null);
  const taskAbortRef = useRef<AbortController | null>(null);
  const callbackHandled = useRef(false);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (callbackHandled.current) return;
    let redirect: URL;
    try {
      redirect = new URL(import.meta.env.VITE_ODID_REDIRECT_URI ?? "");
    } catch {
      return;
    }
    if (window.location.origin !== redirect.origin || window.location.pathname !== redirect.pathname) return;
    if (!window.location.search) return;
    callbackHandled.current = true;
    if (!config.auth) {
      window.history.replaceState({}, document.title, redirect.pathname);
      setAuthError("ODID callback received, but the complete public browser configuration is missing.");
      return;
    }
    setAuthBusy(true);
    setAuthError("");
    void completeODIDLogin(window.location.href, config.auth)
      .then((token) => {
        setAccess(token);
        setNotice("Signed in. Loading your active organization memberships.");
      })
      .catch((cause: unknown) => setAuthError(errorMessage(cause)))
      .finally(() => {
        window.history.replaceState({}, document.title, redirect.pathname);
        setAuthBusy(false);
      });
  }, [config.auth]);

  useEffect(() => {
    if (!access || !config.apiBaseUrl) return;
    let active = true;
    setOrganizationBusy(true);
    setOrganizationError("");
    void listNexusOrganizations(config.apiBaseUrl, access.accessToken)
      .then((result) => {
        if (!active) return;
        setOrganizations(result.organizations);
        setNotice(result.organizations.length
          ? "Choose an organization, then load its authorized projects."
          : "This identity has no active organization memberships.");
      })
      .catch((cause: unknown) => {
        if (active) setOrganizationError(errorMessage(cause));
      })
      .finally(() => {
        if (active) setOrganizationBusy(false);
      });
    return () => { active = false; };
  }, [access, config.apiBaseUrl]);

  useEffect(() => {
    if (!access || !config.apiBaseUrl || !organizationId || !projectId) {
      setConversations([]); setConversationId(""); return;
    }
    let active = true;
    setConversationBusy(true); setMessages([]); setConversationId("");
    void listNexusConversations(config.apiBaseUrl, organizationId, projectId, access.accessToken)
      .then(async (items) => {
        if (!active) return;
        setConversations(items);
        if (items.length > 0) {
          const latest = await getNexusConversation(config.apiBaseUrl, organizationId, projectId, access.accessToken, items[0].conversation_id);
          if (!active) return;
          setConversationId(latest.conversation_id);
          setMessages(latest.messages.map((message) => ({ id: message.message_id, role: message.role, content: message.content })));
          setNotice("Loaded your most recent saved conversation.");
        } else { setNotice("No saved conversations in this project. Start a new conversation."); }
      })
      .catch((cause: unknown) => { if (active) setChatError(errorMessage(cause)); })
      .finally(() => { if (active) setConversationBusy(false); });
    return () => { active = false; };
  }, [access, config.apiBaseUrl, organizationId, projectId]);
  useEffect(() => {
    if (!access) return;
    const remaining = access.expiresAt - Date.now();
    if (remaining <= 0) {
      setAccess(null);
      setOrganizations([]);
      setOrganizationId("");
      setProjects([]);
      setProjectId("");
      setMessages([]);
      setTaskPlan(null);
      setTaskError("");
      setNotice("Your sign-in expired. Sign in again.");
      return;
    }
    const timer = window.setTimeout(() => {
      setAccess(null);
      setOrganizations([]);
      setOrganizationId("");
      setProjects([]);
      setProjectId("");
      setMessages([]);
      setTaskPlan(null);
      setTaskError("");
      setNotice("Your sign-in expired. Sign in again.");
    }, remaining);
    return () => window.clearTimeout(timer);
  }, [access]);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  async function signIn() {
    if (!config.auth) {
      setAuthError("ODID browser authentication is not configured. Set the required VITE_* environment values and register the exact redirect URI.");
      return;
    }
    setAuthBusy(true);
    setAuthError("");
    try {
      const url = await beginODIDLogin(config.auth);
      window.location.assign(url);
    } catch (cause) {
      setAuthError(errorMessage(cause));
      setAuthBusy(false);
    }
  }

  async function loadProjects() {
    if (!access || !config.apiBaseUrl) return;
    setProjectBusy(true);
    setProjectError("");
    setProjects([]);
    setProjectId("");
    setMessages([]);
    setConversations([]);
    setConversationId("");
    setTaskPlan(null);
    setTaskError("");
    setConsent(false);
    try {
      const result = await listNexusProjects(config.apiBaseUrl, organizationId, access.accessToken);
      setProjects(result.projects);
      setNotice(result.projects.length ? "Choose a project to begin a read-only NEXUS conversation." : "No active projects are available to this identity in that organization.");
    } catch (cause) {
      setProjectError(errorMessage(cause));
    } finally {
      setProjectBusy(false);
    }
  }

  async function planTask() {
    const goal = draft.trim();
    if (!access || !projectId || !consent || !goal || taskBusy || sending || !config.apiBaseUrl) return;
    if (goal.length > 8_000) {
      setTaskError("Task descriptions are limited to 8,000 characters.");
      return;
    }
    const projectContext = attachActiveFile && activeFile
      ? "Selected file: " + activeFile.path + "\n" + activeFile.content.slice(0, 8_000)
      : "";
    const controller = new AbortController();
    taskAbortRef.current = controller;
    setTaskBusy(true);
    setTaskError("");
    setChatError("");
    try {
      const task = await createNexusTask(
        config.apiBaseUrl, organizationId, projectId, access.accessToken,
        goal, projectContext, controller.signal,
      );
      setTaskPlan(task);
      setDraft("");
      setConsent(false);
      setNotice("NEXUS created an approval-ready plan. No files or commands have been changed.");
    } catch (cause) {
      if (!controller.signal.aborted) setTaskError(errorMessage(cause));
    } finally {
      if (taskAbortRef.current === controller) taskAbortRef.current = null;
      setTaskBusy(false);
    }
  }

  async function approveTaskPlan() {
    if (!access || !taskPlan || !config.apiBaseUrl || taskBusy) return;
    setTaskBusy(true);
    setTaskError("");
    try {
      const updated = await approveNexusTask(
        config.apiBaseUrl, organizationId, projectId,
        access.accessToken, taskPlan.task_id, taskPlan.version,
      );
      setTaskPlan(updated);
      setNotice("Project owner approval recorded. Execution is not enabled; no files or commands were changed.");
    } catch (cause) {
      setTaskError(errorMessage(cause));
    } finally {
      setTaskBusy(false);
    }
  }

  async function cancelTaskPlan() {
    if (!access || !taskPlan || !config.apiBaseUrl || taskBusy) return;
    setTaskBusy(true);
    setTaskError("");
    try {
      const updated = await cancelNexusTask(
        config.apiBaseUrl, organizationId, projectId,
        access.accessToken, taskPlan.task_id, taskPlan.version,
      );
      setTaskPlan(updated);
      setNotice("Task cancelled.");
    } catch (cause) {
      setTaskError(errorMessage(cause));
    } finally {
      setTaskBusy(false);
    }
  }

  function signOut() {
    abortRef.current?.abort();
    abortRef.current = null;
    taskAbortRef.current?.abort();
    taskAbortRef.current = null;
    setAccess(null);
    setOrganizations([]);
    setOrganizationId("");
    setProjects([]);
    setProjectId("");
    setMessages([]);
    setConversations([]);
    setConversationId("");
    setTaskPlan(null);
    setTaskError("");
    setDraft("");
    setConsent(false);
    setAttachActiveFile(false);
    setChatError("");
    setProjectError("");
    setNotice("Signed out. The in-memory access token and conversation were cleared.");
  }

  async function submitMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = draft.trim();
    if (!access || !projectId || !consent || !content || sending || conversationBusy || !config.apiBaseUrl) return;
    if (content.length > 8_000) {
      setChatError("Messages are limited to 8,000 characters.");
      return;
    }
    const excerpt = attachActiveFile && activeFile
      ? [{ path: activeFile.path, content: activeFile.content.slice(0, 8_000) }]
      : [];
    const next: TranscriptMessage[] = [
      ...messages,
      { id: newMessageId(), role: "user" as const, content },
    ].slice(-20);
    setMessages(next);
    setDraft("");
    setConsent(false);
    setChatError("");
    setSending(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      let activeConversationId = conversationId;
      if (!activeConversationId) {
        const created = await createNexusConversation(config.apiBaseUrl, organizationId, projectId, access.accessToken, content.slice(0, 120) || "NEXUS conversation");
        activeConversationId = created.conversation_id;
        setConversationId(activeConversationId);
        setConversations((current) => [{ conversation_id: created.conversation_id, title: created.title, version: created.version, message_count: created.messages.length, updated_at: created.updated_at }, ...current].slice(0, 30));
      }
      const response = await sendNexusChat({
        apiBaseUrl: config.apiBaseUrl,
        organizationId,
        projectId,
        accessToken: access.accessToken,
        conversationId: activeConversationId,
        messages: next.map(({ role, content: text }) => ({ role, content: text })),
        workspaceFiles: excerpt,
        cloudModelConsent: true,
        signal: controller.signal,
      });
      setMessages((current) => [
        ...current,
        { id: newMessageId(), role: "assistant" as const, content: response.answer },
      ].slice(-20));
      setNotice("Saved response from " + response.model + ". Conversation history is stored in your authorized project.");
    } catch (cause) {
      if (controller.signal.aborted) {
        setNotice("Client request aborted. The current API does not guarantee provider-side cancellation.");
      } else {
        setChatError(errorMessage(cause));
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setSending(false);
    }
  }

  const selectedProject = projects.find((item) => item.project_id === projectId);

  return (
    <aside className={`nexus-pane${isOpen ? "" : " nexus-pane-hidden"}`} aria-label="NEXUS AI chat panel">
      <div className="pane-heading">
        <div><span className="pane-kicker">ODEI NEXUS</span><strong>AI Chat</strong></div>
        <div className="nexus-header-actions">
          {access && <button className="nexus-link-button" onClick={signOut}>Sign out</button>}
          <button className="icon-button" aria-label="Close NEXUS chat" onClick={onClose}>×</button>
        </div>
      </div>

      {!access && (
        <section className="nexus-connection">
          <div className="nexus-mark">N</div>
          <h2>Connect NEXUS</h2>
          <p>Authenticate with your organization identity provider. The access token stays in memory and is never saved in browser storage.</p>
          {config.missing.length > 0 && (
            <div className="nexus-config-warning" role="status">
              Authentication is safely disabled until these deployment settings are configured:
              <code>{config.missing.join(", ")}</code>
            </div>
          )}
          {authError && <p className="nexus-error" role="alert">{authError}</p>}
          <button className="primary-button" disabled={authBusy || !config.auth} onClick={() => void signIn()}>
            {authBusy ? "Connecting…" : "Sign in with ODID"}
          </button>
        </section>
      )}

      {access && (
        <section className="nexus-project-context">
          <div className="nexus-auth-status"><span className="nexus-online-dot" /> Signed in · token held in memory</div>
          <div className="nexus-org-form">
            <label htmlFor="nexus-org-id">ORGANIZATION</label>
            <select id="nexus-org-id" value={organizationId} onChange={(event) => {
              setOrganizationId(event.target.value);
              setProjects([]);
              setProjectId("");
              setTaskPlan(null);
              setTaskError("");
              setMessages([]);
              setConversationBusy(true);
              setConsent(false);
              setProjectError("");
            }} disabled={organizationBusy || organizations.length === 0}>
              <option value="">{organizationBusy ? "Loading memberships…" : "Choose an organization…"}</option>
              {organizations.map((organization) => (
                <option key={organization.organization_id} value={organization.organization_id}>
                  {organization.organization_id} · {organization.role}
                </option>
              ))}
            </select>
          </div>
          {organizationError && <p className="nexus-error" role="alert">{organizationError}</p>}
          {organizationId && (
            <button className="nexus-secondary-button nexus-load-projects" type="button"
              onClick={() => void loadProjects()} disabled={projectBusy}>
              {projectBusy ? "Loading projects…" : "Load projects"}
            </button>
          )}
          {projectError && <p className="nexus-error" role="alert">{projectError}</p>}
          {projects.length > 0 && (
            <label className="nexus-project-select" htmlFor="nexus-project-id">
              <span>PROJECT</span>
              <select id="nexus-project-id" value={projectId} onChange={(event) => {
                setProjectId(event.target.value);
                setTaskPlan(null);
                setTaskError("");
                setMessages([]);
                setConversationBusy(true);
                setConsent(false);
                setChatError("");
              }}>
                <option value="">Choose an authorized project…</option>
                {projects.map((project) => <option key={project.project_id} value={project.project_id}>{project.name}</option>)}
              </select>
            </label>
          )}
          {selectedProject && <p className="nexus-selected-project">Project: <strong>{selectedProject.name}</strong></p>}
          {selectedProject && (
            <div className="nexus-conversation-controls">
              <label htmlFor="nexus-conversation-id">CONVERSATION HISTORY</label>
              <select id="nexus-conversation-id" value={conversationId} disabled={conversationBusy || sending}
                onChange={async (event) => {
                  const selected = event.target.value;
                  if (!selected) { setConversationId(""); setMessages([]); return; }
                  setConversationBusy(true);
                  try {
                    const item = await getNexusConversation(config.apiBaseUrl, organizationId, projectId, access!.accessToken, selected);
                    setConversationId(item.conversation_id);
                    setMessages(item.messages.map((message) => ({ id: message.message_id, role: message.role, content: message.content })));
                    setChatError("");
                  } catch (cause) { setChatError(errorMessage(cause)); }
                  finally { setConversationBusy(false); }
                }}>
                <option value="">New conversation</option>
                {conversations.map((item) => <option key={item.conversation_id} value={item.conversation_id}>{item.title}</option>)}
              </select>
              <div className="nexus-conversation-actions">
                <button type="button" className="nexus-link-button" disabled={sending || conversationBusy}
                  onClick={() => { setConversationId(""); setMessages([]); setDraft(""); setChatError(""); }}>
                  New
                </button>
                {conversationId && (
                  <button type="button" className="nexus-link-button" disabled={sending || conversationBusy}
                    onClick={async () => {
                      if (!window.confirm("Delete this saved conversation permanently?")) return;
                      setConversationBusy(true);
                      try {
                        await deleteNexusConversation(config.apiBaseUrl, organizationId, projectId, access!.accessToken, conversationId);
                        setConversations((items) => items.filter((item) => item.conversation_id !== conversationId));
                        setConversationId("");
                        setMessages([]);
                        setNotice("Saved conversation deleted.");
                      } catch (cause) { setChatError(errorMessage(cause)); }
                      finally { setConversationBusy(false); }
                    }}>
                    Delete
                  </button>
                )}
              </div>
            </div>
          )}
        </section>
      )}

      <div className="nexus-transcript" role="log" aria-label="Conversation" aria-live="polite">
        {messages.length === 0 && (
          <div className="nexus-empty-state">
            <div className="nexus-mark">N</div>
            <h2>Your coding agent</h2>
            <p>{selectedProject ? "Ask a question about your project. NEXUS is currently read-only." : notice}</p>
          </div>
        )}
        {messages.map((message) => (
          <article key={message.id} className={`nexus-message nexus-message-${message.role}`}>
            <strong>{message.role === "user" ? "YOU" : "NEXUS"}</strong>
            <p>{message.content}</p>
          </article>
        ))}
        {taskPlan && (
          <section className="nexus-task-plan" aria-label="NEXUS task plan">
            <div className="nexus-task-heading">
              <strong>APPROVAL-READY PLAN</strong>
              <span>{taskPlan.status.replaceAll("_", " ")}</span>
            </div>
            <p>{taskPlan.goal}</p>
            <pre>{taskPlan.plan ?? "No plan text is available."}</pre>
            {taskPlan.status === "awaiting_approval" && (
              <button type="button" className="nexus-secondary-button" onClick={() => void approveTaskPlan()} disabled={taskBusy}>
                {taskBusy ? "Saving…" : "Approve plan"}
              </button>
            )}
            {["awaiting_approval", "approved"].includes(taskPlan.status) && (
              <button type="button" className="nexus-link-button" onClick={() => void cancelTaskPlan()} disabled={taskBusy}>
                Cancel task
              </button>
            )}
            <p className="nexus-task-safety">Approval records intent only. Task execution, file writes and command execution are not enabled.</p>
            <small>Task ID: {taskPlan.task_id} · Version {taskPlan.version}</small>
          </section>
        )}
        {conversationBusy && <div className="nexus-thinking" role="status">Loading saved conversations…</div>}
        {sending && <div className="nexus-thinking" role="status">NEXUS is thinking…</div>}
        <div ref={transcriptEndRef} />
      </div>

      <div className="nexus-composer-wrap">
        {access && projectId ? (
          <>
            {activeFile && (
              <label className="nexus-attach-toggle">
                <input type="checkbox" checked={attachActiveFile} onChange={(event) => setAttachActiveFile(event.target.checked)} />
                Attach active file excerpt: {activeFile.path}
              </label>
            )}
            {attachActiveFile && activeFile && activeFile.content.length > 8_000 && (
              <p className="nexus-muted">Only the first 8,000 characters of the selected file will be shared.</p>
            )}
            <label className="nexus-consent">
              <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
              I consent to sending this message{attachActiveFile && activeFile ? " and the selected file excerpt" : ""} to the configured cloud AI provider.
            </label>
            <form className="chat-composer" onSubmit={(event) => void submitMessage(event)}>
              <textarea
                aria-label="NEXUS message"
                placeholder="Ask NEXUS about this project…"
                rows={3}
                maxLength={8_000}
                value={draft}
                disabled={sending || taskBusy || conversationBusy || !consent}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
              />
              <div>
                <span>Read-only · durable project history</span>
                {sending
                  ? <button type="button" onClick={() => abortRef.current?.abort()}>Stop</button>
                  : <button type="submit" disabled={!draft.trim() || !consent || conversationBusy || taskBusy}>Send</button>}
                <button type="button" className="nexus-secondary-button" onClick={() => void planTask()}
                  disabled={!draft.trim() || !consent || conversationBusy || sending || taskBusy}>
                  {taskBusy ? "Working…" : "Plan task"}
                </button>
              </div>
            </form>
          </>
        ) : (
          <div className="nexus-composer-locked">Sign in and select an authorized project to enable chat.</div>
        )}
        {chatError && <p className="nexus-error" role="alert">{chatError}</p>}
        {taskError && <p className="nexus-error" role="alert">{taskError}</p>}
        <p className="nexus-disclaimer">{notice}</p>
      </div>
    </aside>
  );
}
