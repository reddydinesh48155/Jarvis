export interface KnowledgeDocument {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: string;
  uploaded_at: string;
  chunk_count: number;
}

export interface DocumentListResponse {
  documents: KnowledgeDocument[];
}
