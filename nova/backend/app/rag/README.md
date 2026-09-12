# NOVA Part 6 RAG assumptions and TODOs

## Design choices

- PostgreSQL with the `pgvector/pgvector:pg16` image is the vector store. The
  user and document filters are applied in the same query as vector retrieval,
  so a chunk from another user is never a candidate. SQLite is supported only
  as a test fallback; it stores vectors as JSON and computes cosine similarity
  in Python.
- Ollama `nomic-embed-text` is the default local embedding model. It is free,
  works without a paid API, and its 768-dimensional vectors are practical for
  a Windows machine with 16 GB RAM. Run `ollama pull nomic-embed-text` before
  indexing production documents.
- A deterministic hashing embedder is used only as an offline fallback when
  Ollama is unavailable. It supports lexical retrieval and reliable tests but
  is not a semantic model.
- Chunks use a configurable character budget (900 by default) and 120
  characters of overlap. PDF page numbers and DOCX heading sections are kept
  in each chunk for citations.
- Retrieval combines vector similarity (65%) with token overlap and metadata
  matches (35%). The current reranker is intentionally a lightweight lexical
  heuristic; a cross-encoder can be added later if local latency and memory
  budgets allow it.

## Operational assumptions and TODOs

- Uploads are capped at 10 MiB by default. There is no object-storage copy in
  Part 6; extracted text and embeddings are persisted in PostgreSQL.
- OCR for scanned PDFs, legacy `.doc` files, spreadsheets, image files, and
  per-document access-control lists are outside this part.
- The Ollama embedding model must remain fixed at 768 dimensions after the
  migration is applied. Changing models requires a migration/reindex plan.
- A background indexing queue, progress persistence, observability, and
  incremental document versioning remain TODOs for a later hardening pass.
- Part 7 long-term memory is deliberately not used: conversation history is
  not indexed and RAG retrieval only searches uploaded document chunks.
