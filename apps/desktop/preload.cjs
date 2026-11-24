const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("odeiDesktop", Object.freeze({
  settings: Object.freeze({
    get: () => ipcRenderer.invoke("odei:settings:get"),
    setODIDSignIn: (enabled) => ipcRenderer.invoke("odei:settings:set-odid-sign-in", enabled),
  }),
  window: Object.freeze({
    minimize: () => ipcRenderer.invoke("odei:window:minimize"),
    toggleMaximize: () => ipcRenderer.invoke("odei:window:toggle-maximize"),
    close: () => ipcRenderer.invoke("odei:window:close"),
    state: () => ipcRenderer.invoke("odei:window:state"),
  }),
  workspace: Object.freeze({
    select: () => ipcRenderer.invoke("odei:workspace:select"),
    current: () => ipcRenderer.invoke("odei:workspace:current"),
    files: () => ipcRenderer.invoke("odei:workspace:files"),
    readFile: (relativePath) => ipcRenderer.invoke("odei:workspace:read-file", relativePath),
  }),
  git: Object.freeze({
    status: () => ipcRenderer.invoke("odei:git:status"),
    diff: (path) => ipcRenderer.invoke("odei:git:diff", path),
    stage: (paths) => ipcRenderer.invoke("odei:git:stage", paths),
    unstage: (paths) => ipcRenderer.invoke("odei:git:unstage", paths),
    commit: (message) => ipcRenderer.invoke("odei:git:commit", message),
  }),
  terminal: Object.freeze({
    open: (options) => ipcRenderer.invoke("odei:terminal:open", options),
    write: (id, data) => ipcRenderer.invoke("odei:terminal:write", id, data),
    resize: (id, cols, rows) => ipcRenderer.invoke("odei:terminal:resize", id, cols, rows),
    close: (id) => ipcRenderer.invoke("odei:terminal:close", id),
    onData: (listener) => {
      if (typeof listener !== "function") throw new TypeError("A terminal data listener is required");
      const handler = (_event, payload) => listener(payload);
      ipcRenderer.on("odei:terminal:data", handler);
      return () => ipcRenderer.removeListener("odei:terminal:data", handler);
    },
  }),
  browser: Object.freeze({
    create: () => ipcRenderer.invoke("odei:browser:create"),
    navigate: (url) => ipcRenderer.invoke("odei:browser:navigate", url),
    back: () => ipcRenderer.invoke("odei:browser:back"),
    forward: () => ipcRenderer.invoke("odei:browser:forward"),
    reload: () => ipcRenderer.invoke("odei:browser:reload"),
    setBounds: (bounds) => ipcRenderer.invoke("odei:browser:set-bounds", bounds),
    close: () => ipcRenderer.invoke("odei:browser:close"),
    onState: (listener) => {
      if (typeof listener !== "function") throw new TypeError("A browser state listener is required");
      const handler = (_event, payload) => listener(payload);
      ipcRenderer.on("odei:browser:state", handler);
      return () => ipcRenderer.removeListener("odei:browser:state", handler);
    },
  }),
  openExternal: (url) => ipcRenderer.invoke("odei:open-external", url),
}));
