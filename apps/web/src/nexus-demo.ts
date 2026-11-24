export type NexusDemoMode = "ask" | "plan" | "agent" | "debug";

/** Static, truthful UI fixture. This function performs no network or model calls. */
export function buildNexusLocalDemoReply(mode: NexusDemoMode): string {
  if (mode === "plan") {
    return "Plan-mode UI is available to exercise, but task planning is disabled in local demo mode. Connect ODID and an authorized project to test real planning.";
  }
  if (mode === "agent" || mode === "debug") {
    return `The ${mode} interface is receiving messages correctly. Local demo mode does not inspect files, call tools, execute commands, or access a repository. Connect ODID and an authorized project to test those governed capabilities.`;
  }
  return "Local chat interface test completed. Your message was kept only in this page’s memory. No identity provider, API, model, repository, or external service was contacted.";
}
