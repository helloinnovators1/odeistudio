import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  beginODIDLogin,
  clearODIDLoginTransaction,
  completeODIDLogin,
  ODidOAuthError,
  type ODidOAuthConfig,
} from "./odid-auth";

const config: ODidOAuthConfig = {
  issuer: "https://identity.example.test",
  clientId: "odei-studio-web",
  redirectUri: "https://studio.example.test/auth/callback",
  resource: "https://api.example.test/",
  scopes: ["studio.read", "projects.read"],
};
const discovery = {
  issuer: config.issuer,
  authorization_endpoint: "https://identity.example.test/authorize",
  token_endpoint: "https://identity.example.test/token",
  code_challenge_methods_supported: ["S256"],
};

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
    values,
  };
}

function fakeCrypto(): Crypto {
  let sequence = 0;
  return {
    getRandomValues<T extends ArrayBufferView | null>(array: T): T {
      if (array) {
        const bytes = new Uint8Array(array.buffer, array.byteOffset, array.byteLength);
        bytes.fill(++sequence);
      }
      return array;
    },
    subtle: {
      digest: async (_algorithm: AlgorithmIdentifier, data: BufferSource) => {
        const bytes = new Uint8Array(data as ArrayBuffer);
        const output = new Uint8Array(32);
        output.set(bytes.slice(0, 32));
        return output.buffer;
      },
    } as SubtleCrypto,
  } as Crypto;
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("ODID OAuth PKCE client", () => {
  let storage: ReturnType<typeof memoryStorage>;
  beforeEach(() => {
    storage = memoryStorage();
  });

  it("discovers the exact issuer and starts S256 authorization without storing tokens", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(discovery));
    const authorizationUrl = await beginODIDLogin(config, {
      storage, cryptoProvider: fakeCrypto(), fetcher, now: 1_000,
    });
    const url = new URL(authorizationUrl);
    expect(url.origin).toBe("https://identity.example.test");
    expect(url.searchParams.get("response_type")).toBe("code");
    expect(url.searchParams.get("client_id")).toBe(config.clientId);
    expect(url.searchParams.get("redirect_uri")).toBe(config.redirectUri);
    expect(url.searchParams.get("resource")).toBe(config.resource);
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
    expect(url.searchParams.get("code_challenge")).toBeTruthy();
    expect(url.searchParams.get("state")).toBeTruthy();
    expect(storage.values.size).toBe(1);
    expect([...storage.values.values()].join(" ")).not.toContain("access_token");
    expect(fetcher.mock.calls[0][1]).toMatchObject({
      credentials: "omit", cache: "no-store", redirect: "error",
    });
  });

  it("exchanges a matching callback code with the verifier and keeps the token in memory only", async () => {
    const discoveryFetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(discovery))
      .mockResolvedValueOnce(jsonResponse(discovery))
      .mockResolvedValueOnce(jsonResponse({
        access_token: "ephemeral-access-token", token_type: "Bearer", expires_in: 900,
        scope: "studio.read projects.read",
      }));
    const authorizationUrl = await beginODIDLogin(config, {
      storage, cryptoProvider: fakeCrypto(), fetcher: discoveryFetcher, now: 2_000,
    });
    const authorization = new URL(authorizationUrl);
    const result = await completeODIDLogin(
      `https://studio.example.test/auth/callback?code=one-time-code&state=${authorization.searchParams.get("state")}`,
      config,
      { storage, fetcher: discoveryFetcher, now: 3_000 },
    );
    expect(result).toEqual({
      accessToken: "ephemeral-access-token",
      expiresAt: 903_000,
      scope: "studio.read projects.read",
    });
    const exchange = discoveryFetcher.mock.calls[2][1];
    const body = new URLSearchParams(String(exchange?.body));
    expect(body.get("grant_type")).toBe("authorization_code");
    expect(body.get("client_id")).toBe(config.clientId);
    expect(body.get("code_verifier")).toBeTruthy();
    expect(body.has("client_secret")).toBe(false);
    expect(exchange).toMatchObject({ credentials: "omit", cache: "no-store", redirect: "error" });
    expect(storage.values.size).toBe(0);
  });

  it("preserves exact issuer, redirect and API resource identifiers", async () => {
    const exactConfig = {
      ...config,
      issuer: "https://identity.example.test/",
      redirectUri: "https://studio.example.test/callback",
      resource: "https://api.example.test",
    };
    const exactDiscovery = {
      ...discovery,
      issuer: exactConfig.issuer,
      authorization_endpoint: "https://identity.example.test/authorize",
    };
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(exactDiscovery));
    const url = new URL(await beginODIDLogin(exactConfig, {
      storage, cryptoProvider: fakeCrypto(), fetcher,
    }));
    expect(url.searchParams.get("redirect_uri")).toBe(exactConfig.redirectUri);
    expect(url.searchParams.get("resource")).toBe(exactConfig.resource);
    expect(fetcher.mock.calls[0][0]).toBe("https://identity.example.test/.well-known/openid-configuration");
  });

  it("rejects issuer mismatch and providers without PKCE S256", async () => {
    const wrongIssuer = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({
      ...discovery, issuer: "https://attacker.example.test",
    }));
    await expect(beginODIDLogin(config, {
      storage, cryptoProvider: fakeCrypto(), fetcher: wrongIssuer,
    })).rejects.toThrow("does not match");
    const noPkce = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({
      ...discovery, code_challenge_methods_supported: ["plain"],
    }));
    await expect(beginODIDLogin(config, {
      storage, cryptoProvider: fakeCrypto(), fetcher: noPkce,
    })).rejects.toThrow("PKCE S256");
  });

  it("rejects callback state mismatch and consumes the stored transaction", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(discovery));
    await beginODIDLogin(config, { storage, cryptoProvider: fakeCrypto(), fetcher });
    await expect(completeODIDLogin(
      "https://studio.example.test/auth/callback?code=code&state=wrong",
      config, { storage, fetcher },
    )).rejects.toBeInstanceOf(ODidOAuthError);
    expect(storage.values.size).toBe(0);
    expect(fetcher).toHaveBeenCalledOnce();
  });

  it("rejects callbacks from an unregistered origin before exchanging a code", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(discovery));
    const authorizationUrl = await beginODIDLogin(config, {
      storage, cryptoProvider: fakeCrypto(), fetcher, now: 1_000,
    });
    const state = new URL(authorizationUrl).searchParams.get("state");
    await expect(completeODIDLogin(
      `https://attacker.example.test/auth/callback?code=code&state=${state}`,
      config, { storage, fetcher, now: 2_000 },
    )).rejects.toThrow("does not match the registered redirect URI");
    expect(fetcher).toHaveBeenCalledOnce();
  });

  it("rejects expired transactions and invalid token responses", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(discovery))
      .mockResolvedValueOnce(jsonResponse(discovery))
      .mockResolvedValueOnce(jsonResponse({ access_token: "token", token_type: "MAC", expires_in: 900 }));
    const url = new URL(await beginODIDLogin(config, {
      storage, cryptoProvider: fakeCrypto(), fetcher, now: 1_000,
    }));
    await expect(completeODIDLogin(
      `https://studio.example.test/auth/callback?code=code&state=${url.searchParams.get("state")}`,
      config, { storage, fetcher, now: 700_000 },
    )).rejects.toThrow("invalid or expired");
    expect(fetcher).toHaveBeenCalledOnce();

    const secondStorage = memoryStorage();
    const secondFetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(discovery))
      .mockResolvedValueOnce(jsonResponse(discovery))
      .mockResolvedValueOnce(jsonResponse({ access_token: "token", token_type: "MAC", expires_in: 900 }));
    const secondUrl = new URL(await beginODIDLogin(config, {
      storage: secondStorage, cryptoProvider: fakeCrypto(), fetcher: secondFetcher, now: 1_000,
    }));
    await expect(completeODIDLogin(
      `https://studio.example.test/auth/callback?code=code&state=${secondUrl.searchParams.get("state")}`,
      config, { storage: secondStorage, fetcher: secondFetcher, now: 2_000 },
    )).rejects.toThrow("invalid access-token response");
  });

  it("bounds discovery responses before parsing", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response("x".repeat(32_001)));
    await expect(beginODIDLogin(config, {
      storage, cryptoProvider: fakeCrypto(), fetcher,
    })).rejects.toThrow("discovery response is oversized");
  });

  it("bounds token responses before parsing", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(discovery))
      .mockResolvedValueOnce(jsonResponse(discovery))
      .mockResolvedValueOnce(new Response("x".repeat(16_001)));
    const authorizationUrl = await beginODIDLogin(config, {
      storage, cryptoProvider: fakeCrypto(), fetcher, now: 1_000,
    });
    const state = new URL(authorizationUrl).searchParams.get("state");
    await expect(completeODIDLogin(
      `https://studio.example.test/auth/callback?code=code&state=${state}`,
      config, { storage, fetcher, now: 2_000 },
    )).rejects.toThrow("token response is oversized");
  });

  it("clears a pending login transaction", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(discovery));
    await beginODIDLogin(config, { storage, cryptoProvider: fakeCrypto(), fetcher });
    clearODIDLoginTransaction(storage);
    expect(storage.values.size).toBe(0);
  });
});
