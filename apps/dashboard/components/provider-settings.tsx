"use client";

import { useCallback, useEffect, useState } from "react";

import type { ProviderStatus } from "@/lib/api";

const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  google: "Google Gemini",
  groq: "Groq",
  mistral: "Mistral",
  openrouter: "OpenRouter",
  ollama: "Ollama (local)",
};

interface SettingsState {
  providers: ProviderStatus[];
  loading: boolean;
  error: string | null;
  notice: string | null;
}

function label(provider: string): string {
  return PROVIDER_LABELS[provider] ?? provider;
}

/**
 * Manual API-key management: paste a key per provider, save or remove it.
 * Keys travel only to the API (server-side proxy) and come back masked.
 */
export function ProviderSettings() {
  const [state, setState] = useState<SettingsState>({
    providers: [],
    loading: true,
    error: null,
    notice: null,
  });
  const [keyDrafts, setKeyDrafts] = useState<Record<string, string>>({});
  const [baseDrafts, setBaseDrafts] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      const response = await fetch("/api/settings/providers", {
        cache: "no-store",
      });
      if (!response.ok) {
        const body = (await response.json()) as { error?: string };
        throw new Error(body.error ?? `request failed (${response.status})`);
      }
      const data = (await response.json()) as { items: ProviderStatus[] };
      setState((prev) => ({
        ...prev,
        providers: data.items,
        loading: false,
        error: null,
      }));
    } catch (error) {
      setState((prev) => ({
        ...prev,
        loading: false,
        error: error instanceof Error ? error.message : "unknown error",
      }));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function save(provider: string) {
    const apiKey = keyDrafts[provider]?.trim();
    const baseUrl = baseDrafts[provider]?.trim();
    if (!apiKey && !baseUrl) {
      setState((prev) => ({
        ...prev,
        error: null,
        notice: "Enter a key (or a base URL for Ollama) first.",
      }));
      return;
    }
    setState((prev) => ({ ...prev, error: null, notice: null }));
    try {
      const response = await fetch(`/api/settings/providers/${provider}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...(apiKey ? { api_key: apiKey } : {}),
          ...(baseUrl ? { base_url: baseUrl } : {}),
        }),
      });
      const body = (await response.json()) as { error?: string };
      if (!response.ok) {
        throw new Error(body.error ?? `save failed (${response.status})`);
      }
      setKeyDrafts((prev) => ({ ...prev, [provider]: "" }));
      setBaseDrafts((prev) => ({ ...prev, [provider]: "" }));
      setState((prev) => ({
        ...prev,
        notice: `${label(provider)} saved - new tasks will use it.`,
      }));
      await load();
    } catch (error) {
      setState((prev) => ({
        ...prev,
        error: error instanceof Error ? error.message : "save failed",
      }));
    }
  }

  async function remove(provider: string) {
    setState((prev) => ({ ...prev, error: null, notice: null }));
    try {
      const response = await fetch(`/api/settings/providers/${provider}`, {
        method: "DELETE",
      });
      const body = (await response.json()) as { error?: string };
      if (!response.ok) {
        throw new Error(body.error ?? `remove failed (${response.status})`);
      }
      setState((prev) => ({
        ...prev,
        notice: `${label(provider)} removed.`,
      }));
      await load();
    } catch (error) {
      setState((prev) => ({
        ...prev,
        error: error instanceof Error ? error.message : "remove failed",
      }));
    }
  }

  if (state.loading) return <p className="muted">Loading providers…</p>;

  return (
    <div>
      {state.error ? <p className="error">{state.error}</p> : null}
      {state.notice ? <p className="muted">{state.notice}</p> : null}
      <ul className="task-list">
        {state.providers.map((provider) => (
          <li
            key={provider.provider}
            className="task-row"
            style={{
              flexDirection: "column",
              alignItems: "stretch",
              gap: 8,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 10,
              }}
            >
              <span className="task-title">{label(provider.provider)}</span>
              <span className="status">
                {provider.configured
                  ? provider.source === "env"
                    ? "env key"
                    : "saved"
                  : "not set"}
              </span>
            </div>
            <div className="muted" style={{ fontSize: 13 }}>
              {provider.key_masked
                ? `Key: ${provider.key_masked}`
                : "No key saved"}
              {provider.base_url ? ` · endpoint: ${provider.base_url}` : ""}
              {provider.source === "env"
                ? " · set via environment (overrides saved)"
                : ""}
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <input
                type="password"
                autoComplete="off"
                placeholder={
                  provider.key_masked ? "paste a new key to replace" : "API key"
                }
                value={keyDrafts[provider.provider] ?? ""}
                onChange={(event) =>
                  setKeyDrafts((prev) => ({
                    ...prev,
                    [provider.provider]: event.target.value,
                  }))
                }
                style={{ flex: "1 1 220px" }}
              />
              {provider.provider === "ollama" ? (
                <input
                  type="text"
                  autoComplete="off"
                  placeholder={provider.base_url ?? "http://localhost:11434"}
                  value={baseDrafts[provider.provider] ?? ""}
                  onChange={(event) =>
                    setBaseDrafts((prev) => ({
                      ...prev,
                      [provider.provider]: event.target.value,
                    }))
                  }
                  style={{ flex: "1 1 200px" }}
                />
              ) : null}
              <button type="button" onClick={() => void save(provider.provider)}>
                Save
              </button>
              {provider.stored ? (
                <button
                  type="button"
                  onClick={() => void remove(provider.provider)}
                >
                  Remove
                </button>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
