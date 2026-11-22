import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  beginODIDLogin,
  completeODIDLogin,
  type ODidAccessToken,
  type ODidOAuthConfig,
} from "./odid-auth";
import { listNexusOrganizations, listNexusProjects, type NexusOrganization, type NexusProject } from "./projects";
import { createNexusConversation, deleteNexusConversation, getNexusConversation, listNexusConversations, sendNexusChatInspection, sendNexusChatStream, type NexusChatMessage, type NexusConversationSummary } from "./nexus-chat";
import { approveNexusTask, cancelNexusTask, createNexusTask, type NexusTask } from "./nexus-tasks";
import { readWorkspaceFile, type CompanionFile } from "./companion";
import { buildWorkspaceArchive } from "./workspace-archive";
import {
  cancelNexusExecution,
  createNexusExecution,
  getNexusExecution,
  getNexusExecutionArtifacts,
  listNexusExecutionProfiles,
  type NexusExecutionArtifacts,
  type NexusExecutionProfile,
  type NexusExecutionRun,
} from "./nexus-executions";
import {
  approveNexusPatchProposal,
  getNexusPatchProposal,
  listNexusPatchProposals,
  rejectNexusPatchProposal,
  type NexusPatchProposal,
  type NexusPatchProposalSummary,
} from "./nexus-patch-proposals";
import "./nexus-chat-panel.css";

interface Props {
  onClose: () => void;
  isOpen?: boolean;
  activeFile?: { path: string; content: string } | null;
  workspaceContext?: { accessToken: string; workspaceId: string; files: CompanionFile[] } | null;
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

export default function NexusChatPanel({
  onClose, isOpen = true, activeFile = null, workspaceContext = null,
}: Props) {
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
  const [useAttachedTools, setUseAttachedTools] = useState(false);
  const [inspectionRunning, setInspectionRunning] = useState(false);
  const [sending, setSending] = useState(false);
  const [chatError, setChatError] = useState("");
  const [taskPlan, setTaskPlan] = useState<NexusTask | null>(null);
  const [taskBusy, setTaskBusy] = useState(false);
  const [taskError, setTaskError] = useState("");
  const [executionProfiles, setExecutionProfiles] = useState<NexusExecutionProfile[]>([]);
  const [executionProfileId, setExecutionProfileId] = useState("");
  const [executionBusy, setExecutionBusy] = useState(false);
  const [executionError, setExecutionError] = useState("");
  const [workspaceUploadConsent, setWorkspaceUploadConsent] = useState(false);
  const [codeExecutionConsent, setCodeExecutionConsent] = useState(false);
  const [executionRun, setExecutionRun] = useState<NexusExecutionRun | null>(null);
  const [executionArtifacts, setExecutionArtifacts] = useState<NexusExecutionArtifacts | null>(null);
  const [snapshotSummary, setSnapshotSummary] = useState("");
  const executionAbortRef = useRef<AbortController | null>(null);
  const executionGenerationRef = useRef(0);
  const [patchProposals, setPatchProposals] = useState<NexusPatchProposalSummary[]>([]);
  const [selectedPatch, setSelectedPatch] = useState<NexusPatchProposal | null>(null);
  const [patchBusy, setPatchBusy] = useState(false);
  const [patchError, setPatchError] = useState("");
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
    if (!access || !config.apiBaseUrl || !organizationId || !projectId) {
      setPatchProposals([]);
      setSelectedPatch(null);
      setPatchError("");
      return;
    }
    let active = true;
    setPatchError("");
    void listNexusPatchProposals(config.apiBaseUrl, organizationId, projectId, access.accessToken)
      .then((result) => { if (active) setPatchProposals(result.proposals); })
      .catch((cause: unknown) => { if (active) setPatchError(errorMessage(cause)); });
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
      setConversations([]);
      setConversationId("");
      setTaskPlan(null);
      setTaskError("");
      setExecutionProfiles([]);
      setExecutionProfileId("");
      setExecutionRun(null);
      setExecutionArtifacts(null);
      setExecutionError("");
      setExecutionBusy(false);
      setNotice("Your sign-in expired. Sign in again.");
      return;
    }
    const timer = window.setTimeout(() => {
      executionGenerationRef.current += 1;
      setAccess(null);
      setOrganizations([]);
      setOrganizationId("");
      setProjects([]);
      setProjectId("");
      setMessages([]);
      setConversations([]);
      setConversationId("");
      setTaskPlan(null);
      setExecutionProfiles([]);
      setExecutionProfileId("");
      setExecutionRun(null);
      setExecutionArtifacts(null);
      setExecutionError("");
      setExecutionBusy(false);
      setSnapshotSummary("");
      setWorkspaceUploadConsent(false);
      setCodeExecutionConsent(false);
      setNotice("Your sign-in expired. Sign in again.");
    }, remaining);
    return () => window.clearTimeout(timer);
  }, [access]);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  useEffect(() => {
    setAttachActiveFile(false);
    setUseAttachedTools(false);
  }, [activeFile?.path, activeFile?.content]);

  useEffect(() => {
    const accessToken = access?.accessToken;
    if (!accessToken || !config.apiBaseUrl || !organizationId || !projectId) {
      setExecutionProfiles([]);
      setExecutionProfileId("");
      setExecutionError("");
      return;
    }
    let active = true;
    const controller = new AbortController();
    setExecutionProfiles([]);
    setExecutionProfileId("");
    setExecutionError("");
    void listNexusExecutionProfiles(
      config.apiBaseUrl, organizationId, projectId, accessToken, fetch, controller.signal,
    ).then((profiles) => {
      if (!active) return;
      setExecutionProfiles(profiles);
      setExecutionProfileId((current) =>
        profiles.some((profile) => profile.profile_id === current)
          ? current : profiles[0]?.profile_id ?? "",
      );
      if (profiles.length === 0) setExecutionError("No server-approved execution profiles are configured.");
    }).catch((cause: unknown) => {
      if (active && !controller.signal.aborted) setExecutionError(errorMessage(cause));
    });
    return () => {
      active = false;
      controller.abort();
    };
  }, [access?.accessToken, config.apiBaseUrl, organizationId, projectId]);

  useEffect(() => {
    const accessToken = access?.accessToken;
    const apiBaseUrl = config.apiBaseUrl ?? "";
    const selectedOrganizationId = organizationId ?? "";
    const selectedProjectId = projectId ?? "";
    const runId = executionRun?.run_id ?? "";
    const taskId = executionRun?.task_id ?? "";
    if (!accessToken || !apiBaseUrl || !runId || !taskId
      || !selectedOrganizationId || !selectedProjectId) return;
    let active = true;
    let timer: number | undefined;
    const controller = new AbortController();
    async function pollRun() {
      try {
        const updated = await getNexusExecution(
          apiBaseUrl, selectedOrganizationId, selectedProjectId, taskId, runId,
          accessToken, fetch, controller.signal,
        );
        if (!active) return;
        setExecutionRun(updated);
        const terminal = ["completed", "failed", "cancelled", "expired"].includes(updated.status);
        if (terminal) {
          try {
            const artifacts = await getNexusExecutionArtifacts(
              apiBaseUrl, selectedOrganizationId, selectedProjectId, taskId, runId,
              accessToken, fetch, controller.signal,
            );
            if (active) setExecutionArtifacts(artifacts);
          } catch {
            if (active) setExecutionArtifacts(null);
          }
          const taskStatus = updated.status === "completed" ? "validating"
            : updated.status === "cancelled" ? "cancelled" : "failed";
          setTaskPlan((current) => current && current.task_id === taskId && current.status !== taskStatus
            ? { ...current, status: taskStatus, version: current.version + 1 }
            : current);
          setNotice(updated.status === "completed"
            ? "Sandbox execution finished. The task is now awaiting validation and review."
            : updated.status === "cancelled"
              ? "Execution cancellation completed."
              : "Execution ended without a successful sandbox result.");
          return;
        }
        timer = window.setTimeout(() => void pollRun(), 2_000);
      } catch (cause) {
        if (!active || controller.signal.aborted) return;
        setExecutionError(errorMessage(cause));
        timer = window.setTimeout(() => void pollRun(), 4_000);
      }
    }
    void pollRun();
    return () => {
      active = false;
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [access?.accessToken, config.apiBaseUrl, organizationId, projectId, executionRun?.run_id]);

  useEffect(() => {
    executionGenerationRef.current += 1;
    setWorkspaceUploadConsent(false);
    setCodeExecutionConsent(false);
    setExecutionError("");
  }, [workspaceContext?.workspaceId]);

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
    executionGenerationRef.current += 1;
    abortRef.current?.abort();
    taskAbortRef.current?.abort();
    setTaskPlan(null);
    setTaskError("");
    setProjectBusy(true);
    setProjectError("");
    setProjects([]);
    setProjectId("");
    setMessages([]);
    setConversations([]);
    setConversationId("");
    setTaskPlan(null);
    setTaskError("");
    setExecutionRun(null);
    setExecutionArtifacts(null);
    setExecutionError("");
    setExecutionBusy(false);
    setSnapshotSummary("");
    setWorkspaceUploadConsent(false);
    setCodeExecutionConsent(false);
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
      setExecutionRun(null);
      setExecutionArtifacts(null);
      setSnapshotSummary("");
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
    const controller = new AbortController();
    taskAbortRef.current = controller;
    setTaskBusy(true);
    setTaskError("");
    try {
      const updated = await approveNexusTask(
        config.apiBaseUrl, organizationId, projectId,
        access.accessToken, taskPlan.task_id, taskPlan.version, fetch, controller.signal,
      );
      if (controller.signal.aborted) return;
      setTaskPlan(updated);
      setNotice("Project owner approval recorded. You may now select a local workspace snapshot and explicitly authorize isolated execution.");
    } catch (cause) {
      if (!controller.signal.aborted) setTaskError(errorMessage(cause));
    } finally {
      if (taskAbortRef.current === controller) taskAbortRef.current = null;
      setTaskBusy(false);
    }
  }

  async function startExecution() {
    if (
      !access || !taskPlan || taskPlan.status !== "approved" || !workspaceContext
      || !executionProfileId || !workspaceUploadConsent || !codeExecutionConsent
      || executionBusy || !config.apiBaseUrl
    ) return;
    const generation = executionGenerationRef.current;
    const controller = new AbortController();
    executionAbortRef.current = controller;
    setExecutionBusy(true);
    setExecutionError("");
    setExecutionArtifacts(null);
    try {
      const snapshot = await buildWorkspaceArchive(
        workspaceContext.files,
        (path) => readWorkspaceFile(
          workspaceContext.accessToken, workspaceContext.workspaceId, path,
        ),
      );
      if (controller.signal.aborted || generation !== executionGenerationRef.current) return;
      if (snapshot.skippedCount > 0) {
        const examples = snapshot.skippedPaths.slice(0, 8).join("\n");
        const message = snapshot.skippedCount + " file(s) will be excluded from this snapshot."
          + (examples ? "\n\nExamples:\n" + examples : "")
          + "\n\nContinue with the partial, filtered workspace snapshot?";
        if (!window.confirm(message)) return;
      }
      const created = await createNexusExecution(
        config.apiBaseUrl, organizationId, projectId, taskPlan.task_id,
        access.accessToken,
        {
          profileId: executionProfileId,
          expectedTaskVersion: taskPlan.version,
          snapshotZipBase64: snapshot.base64,
        },
        fetch, controller.signal,
      );
      if (controller.signal.aborted) return;
      if (generation !== executionGenerationRef.current) {
        try {
          await cancelNexusExecution(
            config.apiBaseUrl, organizationId, projectId, taskPlan.task_id,
            created.run_id, access.accessToken,
          );
        } catch {
          // The run remains tenant-scoped and the backend lease/retention controls still apply.
        }
        return;
      }
      const now = new Date().toISOString();
      setExecutionRun({
        run_id: created.run_id, organization_id: organizationId,
        project_id: projectId, task_id: taskPlan.task_id,
        profile_id: created.profile_id, snapshot_sha256: created.snapshot.sha256,
        status: "queued", version: 0, attempts: 0, max_attempts: 3,
        cancel_requested: false, created_at: now, updated_at: now,
      });
      setTaskPlan({ ...taskPlan, status: "executing", version: taskPlan.version + 1 });
      setWorkspaceUploadConsent(false);
      setCodeExecutionConsent(false);
      setSnapshotSummary(
        snapshot.fileCount + " files · " + Math.ceil(snapshot.totalBytes / 1024) + " KiB"
        + (snapshot.skippedCount ? " · " + snapshot.skippedCount + " skipped" : ""),
      );
      setNotice("Workspace snapshot uploaded. The approved server profile has been queued for isolated execution.");
    } catch (cause) {
      if (!controller.signal.aborted && generation === executionGenerationRef.current) {
        setExecutionError(errorMessage(cause));
      }
    } finally {
      if (executionAbortRef.current === controller) executionAbortRef.current = null;
      setExecutionBusy(false);
    }
  }

  async function cancelExecution() {
    if (!access || !executionRun || !config.apiBaseUrl || executionBusy) return;
    const generation = executionGenerationRef.current;
    const controller = new AbortController();
    executionAbortRef.current = controller;
    setExecutionBusy(true);
    setExecutionError("");
    try {
      const updated = await cancelNexusExecution(
        config.apiBaseUrl, organizationId, projectId, executionRun.task_id,
        executionRun.run_id, access.accessToken, fetch, controller.signal,
      );
      if (controller.signal.aborted || generation !== executionGenerationRef.current) return;
      setExecutionRun(updated);
      if (updated.status === "cancelled") {
        setTaskPlan((current) => current && current.task_id === updated.task_id
          && current.status !== "cancelled"
          ? { ...current, status: "cancelled", version: current.version + 1 }
          : current);
      }
      setNotice(updated.status === "cancelled"
        ? "Queued execution and task were cancelled."
        : "Cancellation requested. The worker will terminate the sandbox and confirm cleanup.");
    } catch (cause) {
      if (!controller.signal.aborted && generation === executionGenerationRef.current) {
        setExecutionError(errorMessage(cause));
      }
    } finally {
      if (executionAbortRef.current === controller) executionAbortRef.current = null;
      setExecutionBusy(false);
    }
  }

  async function cancelTaskPlan() {
    if (!access || !taskPlan || !config.apiBaseUrl || taskBusy) return;
    const controller = new AbortController();
    taskAbortRef.current = controller;
    setTaskBusy(true);
    setTaskError("");
    try {
      const updated = await cancelNexusTask(
        config.apiBaseUrl, organizationId, projectId,
        access.accessToken, taskPlan.task_id, taskPlan.version, fetch, controller.signal,
      );
      if (controller.signal.aborted) return;
      setTaskPlan(updated);
      setNotice("Task cancelled.");
    } catch (cause) {
      if (!controller.signal.aborted) setTaskError(errorMessage(cause));
    } finally {
      if (taskAbortRef.current === controller) taskAbortRef.current = null;
      setTaskBusy(false);
    }
  }

  function signOut() {
    abortRef.current?.abort();
    abortRef.current = null;
    taskAbortRef.current?.abort();
    taskAbortRef.current = null;
    executionGenerationRef.current += 1;
    executionAbortRef.current = null;
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
    setExecutionProfiles([]);
    setExecutionProfileId("");
    setExecutionRun(null);
    setExecutionArtifacts(null);
    setExecutionError("");
    setExecutionBusy(false);
    setSnapshotSummary("");
    setWorkspaceUploadConsent(false);
    setCodeExecutionConsent(false);
    setDraft("");
    setConsent(false);
    setAttachActiveFile(false);
    setUseAttachedTools(false);
    setChatError("");
    setProjectError("");
    setNotice("Signed out. The in-memory access token and conversation were cleared.");
  }

  async function loadPatchProposal(proposalId: string) {
    if (!access || !config.apiBaseUrl || !organizationId || !projectId || !proposalId) return;
    setPatchBusy(true);
    setPatchError("");
    try {
      const item = await getNexusPatchProposal(
        config.apiBaseUrl, organizationId, projectId, access.accessToken, proposalId,
      );
      setSelectedPatch(item);
    } catch (cause) {
      setPatchError(errorMessage(cause));
    } finally {
      setPatchBusy(false);
    }
  }

  async function decidePatchProposal(decision: "approve" | "reject") {
    if (!access || !config.apiBaseUrl || !selectedPatch || !selectedPatch.can_decide || patchBusy) return;
    setPatchBusy(true);
    setPatchError("");
    try {
      const decide = decision === "approve" ? approveNexusPatchProposal : rejectNexusPatchProposal;
      await decide(
        config.apiBaseUrl, organizationId, projectId, access.accessToken,
        selectedPatch.proposal_id, selectedPatch.version,
      );
      const updated = await getNexusPatchProposal(
        config.apiBaseUrl, organizationId, projectId, access.accessToken,
        selectedPatch.proposal_id,
      );
      setSelectedPatch(updated);
      setPatchProposals((items) => items.map((item) =>
        item.proposal_id === updated.proposal_id
          ? { ...item, status: updated.status, version: updated.version, updated_at: updated.updated_at }
          : item
      ));
      setNotice(decision === "approve"
        ? "Project owner approval recorded. The local file is unchanged; application is not enabled."
        : "Patch proposal rejected. The local file is unchanged.");
    } catch (cause) {
      setPatchError(errorMessage(cause));
    } finally {
      setPatchBusy(false);
    }
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
    const isInspection = useAttachedTools && excerpt.length > 0;
    setInspectionRunning(isInspection);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      let activeConversationId = conversationId;
      if (!activeConversationId) {
        const created = await createNexusConversation(config.apiBaseUrl, organizationId, projectId, access.accessToken, content.slice(0, 120) || "NEXUS conversation", fetch, controller.signal);
        activeConversationId = created.conversation_id;
        setConversationId(activeConversationId);
        setConversations((current) => [{ conversation_id: created.conversation_id, title: created.title, version: created.version, message_count: created.messages.length, updated_at: created.updated_at }, ...current].slice(0, 30));
      }
      if (isInspection) {
        const inspected = await sendNexusChatInspection({
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
        setMessages((current) => [...current, {
          id: "inspect-" + newMessageId(), role: "assistant" as const, content: inspected.answer,
        }].slice(-20));
        if (inspected.patch_proposal) {
          setPatchProposals((items) => [
            {
              proposal_id: inspected.patch_proposal!.proposal_id,
              title: inspected.patch_proposal!.title,
              status: inspected.patch_proposal!.status,
              version: inspected.patch_proposal!.version,
              file_count: inspected.patch_proposal!.file_count,
              created_at: inspected.patch_proposal!.created_at,
              updated_at: inspected.patch_proposal!.updated_at,
            },
            ...items.filter((item) => item.proposal_id !== inspected.patch_proposal!.proposal_id),
          ].slice(0, 30));
          await loadPatchProposal(inspected.patch_proposal.proposal_id);
          setNotice("NEXUS created a persistent review-only patch proposal. Approval does not apply it to local files.");
        } else {
          setNotice("Read-only inspection completed with " + inspected.tools_executed + " tool calls (" + (inspected.tool_names.join(", ") || "no tools requested") + "). Only the attached excerpt was available.");
        }
        return;
      }
      const assistantId = "stream-" + newMessageId();
      let assistantStarted = false;
      const response = await sendNexusChatStream({
        apiBaseUrl: config.apiBaseUrl,
        organizationId,
        projectId,
        accessToken: access.accessToken,
        conversationId: activeConversationId,
        messages: next.map(({ role, content: text }) => ({ role, content: text })),
        workspaceFiles: excerpt,
        cloudModelConsent: true,
        signal: controller.signal,
      }, (delta) => {
        setMessages((current) => {
          if (!assistantStarted) {
            assistantStarted = true;
            return [...current, { id: assistantId, role: "assistant" as const, content: delta }].slice(-20);
          }
          return current.map((message) => message.id === assistantId
            ? { ...message, content: message.content + delta }
            : message);
        });
      });
      setNotice("Streaming response saved from " + response.model + ". Conversation history is stored in your authorized project.");
    } catch (cause) {
      setMessages((current) => current.filter((message) => !message.id.startsWith("stream-")));
      if (controller.signal.aborted) {
        setNotice(isInspection ? "Inspection cancelled in the browser; server-side model work may finish." : "Stream cancelled. The submitted user turn remains saved; provider cancellation is best-effort.");
      } else {
        setChatError(errorMessage(cause));
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setSending(false);
      setInspectionRunning(false);
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
              abortRef.current?.abort();
              taskAbortRef.current?.abort();
              setTaskPlan(null);
              setTaskError("");
              executionGenerationRef.current += 1;
              setOrganizationId(event.target.value);
              setProjects([]);
              setProjectId("");
              setTaskPlan(null);
              setTaskError("");
              setExecutionRun(null);
              setExecutionArtifacts(null);
              setExecutionError("");
              setSnapshotSummary("");
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
                abortRef.current?.abort();
                taskAbortRef.current?.abort();
                setTaskPlan(null);
                setTaskError("");
                executionGenerationRef.current += 1;
                setProjectId(event.target.value);
                setTaskPlan(null);
                setTaskError("");
                setExecutionRun(null);
                setExecutionArtifacts(null);
                setExecutionError("");
                setSnapshotSummary("");
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
        {selectedPatch && (
          <section className="nexus-patch-review" aria-label="NEXUS patch proposal review">
            <div className="nexus-task-heading">
              <strong>PATCH PROPOSAL REVIEW</strong>
              <span>{selectedPatch.status}</span>
            </div>
            <p>{selectedPatch.title}</p>
            {selectedPatch.files.map((file) => (
              <details key={file.path} className="nexus-patch-file">
                <summary>{file.operation.toUpperCase()} · {file.path}</summary>
                <pre>{file.unified_diff || "No textual diff was generated."}</pre>
              </details>
            ))}
            {selectedPatch.status === "pending" && selectedPatch.can_decide && (
              <div className="nexus-patch-actions">
                <button type="button" className="nexus-secondary-button" disabled={patchBusy}
                  onClick={() => void decidePatchProposal("approve")}>
                  {patchBusy ? "Saving…" : "Approve proposal"}
                </button>
                <button type="button" className="nexus-link-button" disabled={patchBusy}
                  onClick={() => void decidePatchProposal("reject")}>Reject</button>
              </div>
            )}
            {selectedPatch.status === "pending" && !selectedPatch.can_decide && (
              <p className="nexus-task-safety">Awaiting a project-owner decision.</p>
            )}
            <p className="nexus-task-safety">Approval records review intent only. It does not write, apply or delete local files. Application remains disabled.</p>
            <small>Proposal ID: {selectedPatch.proposal_id} · Version {selectedPatch.version}</small>
          </section>
        )}
        {patchProposals.length > 0 && (
          <div className="nexus-proposal-picker">
            <label htmlFor="nexus-patch-proposal-id">PATCH PROPOSALS</label>
            <select id="nexus-patch-proposal-id" value={selectedPatch?.proposal_id ?? ""}
              disabled={patchBusy || sending}
              onChange={(event) => void loadPatchProposal(event.target.value)}>
              <option value="">Select a saved proposal…</option>
              {patchProposals.map((item) => (
                <option key={item.proposal_id} value={item.proposal_id}>
                  {item.status.toUpperCase()} · {item.title}
                </option>
              ))}
            </select>
          </div>
        )}
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
            {["awaiting_approval", "approved", "executing", "validating"].includes(taskPlan.status) && (
              <button type="button" className="nexus-link-button" onClick={() => void cancelTaskPlan()} disabled={taskBusy || executionBusy}>
                Cancel task
              </button>
            )}
            {taskPlan.status === "approved" && !executionRun && (
              <div className="nexus-execution-controls">
                <strong>ISOLATED EXECUTION</strong>
                {!workspaceContext ? (
                  <p className="nexus-muted">Connect the local companion and select a workspace before creating an execution snapshot.</p>
                ) : (
                  <>
                    <p>{workspaceContext.files.length} local files are visible to the companion. A filtered snapshot is created only after both consent checks and your confirmation.</p>
                    {workspaceContext.files.length === 0 && <p className="nexus-muted">No readable files are currently listed for this workspace.</p>}
                    <label className="nexus-execution-label" htmlFor="nexus-execution-profile">Server-approved execution profile</label>
                    <select id="nexus-execution-profile" value={executionProfileId}
                      onChange={(event) => setExecutionProfileId(event.target.value)}
                      disabled={executionBusy || executionProfiles.length === 0}>
                      <option value="">Select an approved profile…</option>
                      {executionProfiles.map((profile) => (
                        <option key={profile.profile_id} value={profile.profile_id}>{profile.profile_id}</option>
                      ))}
                    </select>
                    <label className="nexus-consent nexus-execution-consent">
                      <input type="checkbox" checked={workspaceUploadConsent}
                        onChange={(event) => setWorkspaceUploadConsent(event.target.checked)}
                        disabled={executionBusy} />
                      I explicitly authorize uploading a filtered snapshot of this selected workspace to ODEI for this task.
                    </label>
                    <label className="nexus-consent nexus-execution-consent">
                      <input type="checkbox" checked={codeExecutionConsent}
                        onChange={(event) => setCodeExecutionConsent(event.target.checked)}
                        disabled={executionBusy} />
                      I explicitly authorize running the selected server-approved command profile against that snapshot in an isolated sandbox.
                    </label>
                    <p className="nexus-task-safety">The snapshot excludes known credential paths, dependency/build folders and files larger than 2 MiB. Unreadable files are skipped. No local files are modified.</p>
                    <button type="button" className="nexus-secondary-button"
                      onClick={() => void startExecution()}
                      disabled={executionBusy || workspaceContext.files.length === 0 || !executionProfileId || !workspaceUploadConsent || !codeExecutionConsent}>
                      {executionBusy ? "Preparing snapshot and queueing…" : "Create isolated execution"}
                    </button>
                  </>
                )}
              </div>
            )}
            {executionError && <p className="nexus-error" role="alert">{executionError}</p>}
            {snapshotSummary && <p className="nexus-selected-project">Snapshot: {snapshotSummary}</p>}
            {executionRun && executionRun.task_id === taskPlan.task_id && (
              <div className="nexus-execution-result" aria-live="polite">
                <div className="nexus-task-heading">
                  <strong>EXECUTION RUN</strong>
                  <span>{executionRun.status.toUpperCase()}</span>
                </div>
                <small>Run: {executionRun.run_id}</small>
                <small>Profile: {executionRun.profile_id} · Attempt {executionRun.attempts}/{executionRun.max_attempts}</small>
                <small>Snapshot SHA-256: {executionRun.snapshot_sha256}</small>
                {["queued", "leased", "running", "collecting"].includes(executionRun.status)
                  && !executionRun.cancel_requested && (
                  <button type="button" className="nexus-link-button" onClick={() => void cancelExecution()} disabled={executionBusy}>
                    {executionBusy ? "Requesting…" : "Cancel execution"}
                  </button>
                )}
                {executionRun.cancel_requested && <p className="nexus-muted">Cancellation requested; waiting for sandbox cleanup.</p>}
                {executionArtifacts && (
                  <div className="nexus-execution-artifacts">
                    <p>Exit code: {executionArtifacts.exit_code} · Duration: {executionArtifacts.duration_ms} ms{executionArtifacts.timed_out ? " · Timed out" : ""}</p>
                    <strong>Standard output</strong>
                    <pre>{executionArtifacts.stdout || "(empty)"}</pre>
                    <strong>Standard error</strong>
                    <pre>{executionArtifacts.stderr || "(empty)"}</pre>
                    {(executionArtifacts.stdout_truncated || executionArtifacts.stderr_truncated)
                      && <p className="nexus-muted">Output was truncated by the server safety limit.</p>}
                  </div>
                )}
              </div>
            )}
            <p className="nexus-task-safety">Execution is limited to the server-approved profile and immutable snapshot. Results require validation and review; successful sandbox exit does not automatically complete the task.</p>
            <small>Task ID: {taskPlan.task_id} · Version {taskPlan.version}</small>
          </section>
        )}
        {conversationBusy && <div className="nexus-thinking" role="status">Loading saved conversations…</div>}
        {sending && <div className="nexus-thinking" role="status">{inspectionRunning ? "NEXUS is inspecting attached excerpts…" : "NEXUS is thinking…"}</div>}
        <div ref={transcriptEndRef} />
      </div>

      <div className="nexus-composer-wrap">
        {access && projectId ? (
          <>
            {activeFile && (
              <label className="nexus-attach-toggle">
                <input type="checkbox" checked={attachActiveFile} onChange={(event) => { setAttachActiveFile(event.target.checked); if (!event.target.checked) setUseAttachedTools(false); }} />
                Attach active file excerpt: {activeFile.path}
              </label>
            )}
            {attachActiveFile && activeFile && (
              <label className="nexus-attach-toggle nexus-tools-toggle">
                <input type="checkbox" checked={useAttachedTools}
                  disabled={activeFile.content.length > 8_000}
                  onChange={(event) => setUseAttachedTools(event.target.checked)} />
                Allow NEXUS inspection and review-only change proposals for this attached excerpt
              </label>
            )}
            {attachActiveFile && activeFile && activeFile.content.length > 8_000 && (
              <p className="nexus-muted">Only the first 8,000 characters can be shared. To prevent stale base hashes, repository inspection and generated patch proposals are disabled for this larger file.</p>
            )}
            <label className="nexus-consent">
              <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
              I consent to sending this request{attachActiveFile && activeFile ? " and the selected file excerpt" : ""} to the configured cloud AI provider.
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
                  ? <button type="button" onClick={() => abortRef.current?.abort()}>{inspectionRunning ? "Cancel inspection" : "Stop"}</button>
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
        {patchError && <p className="nexus-error" role="alert">{patchError}</p>}
        <p className="nexus-disclaimer">{notice}</p>
      </div>
    </aside>
  );
}
