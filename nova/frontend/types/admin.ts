export interface AuditLogEntry {
  id: string;
  tool_name: string;
  permission_level: string;
  user_id: string | null;
  success: boolean;
  error_message: string | null;
  requires_confirmation: boolean;
  confirmed: boolean;
  execution_time_ms: number | null;
  created_at?: string | null;
  timestamp?: string | null;
}

export interface AuditLogListResponse {
  logs: AuditLogEntry[];
  total: number;
}

export interface AdminUser {
  id: string;
  email: string;
  role: string;
  created_at: string;
}

export interface UserListResponse {
  users: AdminUser[];
  total: number;
}

