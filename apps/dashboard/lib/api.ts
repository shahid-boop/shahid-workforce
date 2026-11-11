/**
 * Server-side API client for the workforce API.
 *
 * Runs only in Next.js server code (route handlers / server components) so the
 * API key never reaches the browser. Configuration comes from the environment:
 *
 *   WORKFORCE_API_BASE_URL  (default http://127.0.0.1:8000)
 *   WORKFORCE_API_KEY       (required; fail-closed when missing)
 */

export type TaskStatus =
  | "pending"
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface Task {
  id: string;
  title: string;
  description: string | null;
  status: TaskStatus;
  result: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskList {
  items: Task[];
  count: number;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function baseUrl(): string {
  return process.env.WORKFORCE_API_BASE_URL ?? "http://127.0.0.1:8000";
}

function apiKey(): string {
  const key = process.env.WORKFORCE_API_KEY;
  if (!key) {
    throw new ApiError(0, "WORKFORCE_API_KEY is not configured");
  }
  return key;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl()}${path}`, {
    ...init,
    headers: {
      "X-API-Key": apiKey(),
      "Content-Type": "application/json",
      ...init?.headers,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // keep statusText when the body is not JSON
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function listTasks(limit = 50): Promise<TaskList> {
  return request<TaskList>(`/tasks?limit=${limit}`);
}

export async function createTask(input: {
  title: string;
  description?: string;
}): Promise<Task> {
  return request<Task>("/tasks", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function deleteTask(taskId: string): Promise<void> {
  return request<void>(`/tasks/${taskId}`, { method: "DELETE" });
}

export async function getTask(taskId: string): Promise<Task> {
  return request<Task>(`/tasks/${taskId}`);
}

export interface Agent {
  id: string;
  name: string;
  department: string;
  model: string | null;
}

export interface AgentList {
  items: Agent[];
  count: number;
}

export async function listAgents(): Promise<AgentList> {
  return request<AgentList>("/agents");
}

export interface ProviderStatus {
  provider: string;
  configured: boolean;
  source: "env" | "stored" | null;
  key_masked: string | null;
  base_url: string | null;
  stored: boolean;
}

export interface ProviderStatusList {
  items: ProviderStatus[];
  count: number;
}

export async function listProviderStatuses(): Promise<ProviderStatusList> {
  return request<ProviderStatusList>("/settings/providers");
}

export async function saveProviderKey(
  provider: string,
  payload: { api_key?: string; base_url?: string },
): Promise<ProviderStatus> {
  return request<ProviderStatus>(`/settings/providers/${provider}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteProviderKey(
  provider: string,
): Promise<ProviderStatus> {
  return request<ProviderStatus>(`/settings/providers/${provider}`, {
    method: "DELETE",
  });
}

/** Normalise client/transport errors to an HTTP status plus message. */
export function errorInfo(error: unknown): { message: string; status: number } {
  if (error instanceof ApiError) {
    const status = error.status >= 400 && error.status < 600 ? error.status : 502;
    return { message: error.message, status };
  }
  return { message: "upstream request failed", status: 502 };
}
