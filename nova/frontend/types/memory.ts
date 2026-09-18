export interface Memory {
  id: string;
  content: string;
  category: string;
  source_session_id: string | null;
  created_at: string;
  last_accessed_at: string | null;
}

export interface MemoryListResponse {
  memories: Memory[];
  memory_enabled: boolean;
}

export interface MemorySettings {
  memory_enabled: boolean;
}
