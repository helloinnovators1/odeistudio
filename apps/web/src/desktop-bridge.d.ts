export {};

type ODEIGitFile = { index: string; worktree: string; path: string; staged: boolean; unstaged: boolean; untracked: boolean };
type ODEIGitStatus = { branch: string; clean: boolean; files: ODEIGitFile[] };
type ODEIBrowserState = { url: string; canGoBack: boolean; canGoForward: boolean; loading: boolean };
declare global {
  interface Window {
    odeiDesktop?: {
      window: { minimize(): Promise<boolean>; toggleMaximize(): Promise<boolean>; close(): Promise<boolean>; state(): Promise<{ minimized: boolean; maximized: boolean; focused: boolean }> };
      workspace: { select(): Promise<{ name: string } | null>; current(): Promise<{ name: string } | null>; files(): Promise<Array<{ path: string; size: number }>>; readFile(path: string): Promise<string> };
      git: { status(): Promise<ODEIGitStatus>; diff(path?: string): Promise<{ unstaged: string; staged: string }>; stage(paths: string[]): Promise<{ staged: string[] }>; unstage(paths: string[]): Promise<{ unstaged: string[] }>; commit(message: string): Promise<{ commit: string; summary: string }> };
      terminal: { open(options?: { cols?: number; rows?: number }): Promise<{ id: string; cwd: string; shell: string }>; write(id: string, data: string): Promise<boolean>; resize(id: string, cols: number, rows: number): Promise<boolean>; close(id: string): Promise<boolean>; onData(listener: (payload: { id: string; data?: string; exitCode?: number }) => void): () => void };
      browser: { create(): Promise<ODEIBrowserState>; navigate(url: string): Promise<ODEIBrowserState>; back(): Promise<boolean>; forward(): Promise<boolean>; reload(): Promise<boolean>; setBounds(bounds: { x: number; y: number; width: number; height: number }): Promise<boolean>; close(): Promise<boolean>; onState(listener: (state: ODEIBrowserState) => void): () => void };
      openExternal(url: string): Promise<boolean>;
    };
  }
}
