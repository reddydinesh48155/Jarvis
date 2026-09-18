import type { TokenResponse, User } from "@/types/auth";
import type { VoiceTokenResponse } from "@/types/voice";
import type { DocumentListResponse, KnowledgeDocument } from "@/types/rag";
import type { MemoryListResponse, MemorySettings } from "@/types/memory";
import type { AuditLogListResponse, UserListResponse } from "@/types/admin";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? String(payload.detail)
        : "The request could not be completed.";
    throw new ApiError(detail, response.status);
  }

  return payload as T;
}

export function register(email: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function login(email: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function refreshSession(): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/refresh", { method: "POST" });
}

export function logout(): Promise<void> {
  return request<void>("/auth/logout", { method: "POST" });
}

export function getMe(accessToken: string): Promise<User> {
  return request<User>("/auth/me", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function getVoiceToken(accessToken: string): Promise<VoiceTokenResponse> {
  return request<VoiceTokenResponse>("/voice/token", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function listDocuments(accessToken: string): Promise<DocumentListResponse> {
  return request<DocumentListResponse>("/documents", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function uploadDocument(accessToken: string, file: File): Promise<KnowledgeDocument> {
  const body = new FormData();
  body.append("file", file);
  return request<KnowledgeDocument>("/documents", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body,
  });
}

export function deleteDocument(accessToken: string, documentId: string): Promise<void> {
  return request<void>(`/documents/${documentId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function listMemories(accessToken: string): Promise<MemoryListResponse> {
  return request<MemoryListResponse>("/memory", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function deleteMemory(accessToken: string, memoryId: string): Promise<void> {
  return request<void>(`/memory/${memoryId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function clearAllMemories(accessToken: string): Promise<void> {
  return request<void>("/memory", {
    method: "DELETE",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function updateMemorySettings(accessToken: string, enabled: boolean): Promise<MemorySettings> {
  return request<MemorySettings>("/memory/settings", {
    method: "PATCH",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ memory_enabled: enabled }),
  });
}

export function getAuditLogs(
  accessToken: string,
  params?: { limit?: number; offset?: number; tool_name?: string; user_id?: string },
): Promise<AuditLogListResponse> {
  const query = new URLSearchParams();
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  if (params?.tool_name) query.set("tool_name", params.tool_name);
  if (params?.user_id) query.set("user_id", params.user_id);
  const qs = query.toString();
  return request<AuditLogListResponse>(`/admin/audit-logs${qs ? `?${qs}` : ""}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function listUsers(accessToken: string): Promise<UserListResponse> {
  return request<UserListResponse>("/admin/users", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}
