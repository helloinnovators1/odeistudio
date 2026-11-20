import { describe, expect, it } from "vitest";
import {
  CHAT_PANEL_SIDE_STORAGE_KEY,
  DEFAULT_CHAT_PANEL_SIDE,
  isToggleNexusChatShortcut,
  languageForPath,
  normalizeChatPanelSide,
  readChatPanelSide,
  writeChatPanelSide,
} from "./ide-preferences";

describe("NEXUS chat panel preference", () => {
  it("defaults to the right and normalizes invalid values", () => {
    expect(DEFAULT_CHAT_PANEL_SIDE).toBe("right");
    expect(normalizeChatPanelSide("left")).toBe("left");
    expect(normalizeChatPanelSide("unexpected")).toBe("right");
  });

  it("reads and writes the selected side using the stable preference key", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    };
    writeChatPanelSide("left", storage);
    expect(values.get(CHAT_PANEL_SIDE_STORAGE_KEY)).toBe("left");
    expect(readChatPanelSide(storage)).toBe("left");
  });

  it("fails safely when browser storage is unavailable", () => {
    expect(readChatPanelSide({
      getItem: () => { throw new Error("blocked"); },
    })).toBe("right");
    expect(() => writeChatPanelSide("left", {
      setItem: () => { throw new Error("blocked"); },
    })).not.toThrow();
  });

  it("recognizes Command+I and Ctrl+I but not unrelated shortcuts", () => {
    expect(isToggleNexusChatShortcut({
      key: "i", metaKey: true, ctrlKey: false, altKey: false, shiftKey: false,
    })).toBe(true);
    expect(isToggleNexusChatShortcut({
      key: "I", metaKey: false, ctrlKey: true, altKey: false, shiftKey: false,
    })).toBe(true);
    expect(isToggleNexusChatShortcut({
      key: "i", metaKey: true, ctrlKey: false, altKey: false, shiftKey: true,
    })).toBe(false);
  });

  it("maps common source extensions to Monaco languages", () => {
    expect(languageForPath("src/App.tsx")).toBe("typescript");
    expect(languageForPath("server/main.py")).toBe("python");
    expect(languageForPath("README.md")).toBe("markdown");
    expect(languageForPath("notes.unknown")).toBe("plaintext");
  });
});
