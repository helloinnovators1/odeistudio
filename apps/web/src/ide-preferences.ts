export type ChatPanelSide = "left" | "right";

export const CHAT_PANEL_SIDE_STORAGE_KEY = "odei.nexus.chatPanelSide";
export const DEFAULT_CHAT_PANEL_SIDE: ChatPanelSide = "right";

export function normalizeChatPanelSide(value: unknown): ChatPanelSide {
  return value === "left" || value === "right" ? value : DEFAULT_CHAT_PANEL_SIDE;
}

export function readChatPanelSide(storage?: Pick<Storage, "getItem">): ChatPanelSide {
  try {
    const target = storage ?? (typeof window === "undefined" ? undefined : window.localStorage);
    return normalizeChatPanelSide(target?.getItem(CHAT_PANEL_SIDE_STORAGE_KEY));
  } catch {
    return DEFAULT_CHAT_PANEL_SIDE;
  }
}

export function writeChatPanelSide(
  side: ChatPanelSide,
  storage?: Pick<Storage, "setItem">,
): void {
  try {
    const target = storage ?? (typeof window === "undefined" ? undefined : window.localStorage);
    target?.setItem(CHAT_PANEL_SIDE_STORAGE_KEY, normalizeChatPanelSide(side));
  } catch {
    // The preference remains active in memory if browser storage is unavailable.
  }
}

export function isToggleNexusChatShortcut(
  event: Pick<KeyboardEvent, "key" | "metaKey" | "ctrlKey" | "altKey" | "shiftKey">,
): boolean {
  return (
    (event.metaKey || event.ctrlKey) &&
    !event.altKey &&
    !event.shiftKey &&
    event.key.toLowerCase() === "i"
  );
}

export function languageForPath(path: string): string {
  const extension = path.split(".").pop()?.toLowerCase() ?? "";
  const languages: Record<string, string> = {
    c: "c", cc: "cpp", cpp: "cpp", cs: "csharp", css: "css",
    go: "go", html: "html", java: "java", js: "javascript",
    json: "json", jsx: "javascript", md: "markdown", mjs: "javascript",
    php: "php", py: "python", rb: "ruby", rs: "rust", sh: "shell",
    sql: "sql", toml: "ini", ts: "typescript", tsx: "typescript",
    xml: "xml", yaml: "yaml", yml: "yaml",
  };
  return languages[extension] ?? "plaintext";
}
