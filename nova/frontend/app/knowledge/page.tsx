"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/hooks/use-auth";
import { deleteDocument, listDocuments, uploadDocument } from "@/lib/api";
import type { KnowledgeDocument } from "@/types/rag";

const ACCEPTED_TYPES = ".pdf,.txt,.docx,.md,.markdown";

export default function KnowledgePage() {
  const { user, accessToken, isLoading: isAuthLoading } = useAuth();
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadDocuments = useCallback(async () => {
    if (!accessToken) return;
    setIsLoading(true);
    try {
      const response = await listDocuments(accessToken);
      setDocuments(response.documents);
      setError(null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to load indexed documents.");
    } finally {
      setIsLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void loadDocuments();
  }, [loadDocuments]);

  async function handleUpload() {
    if (!accessToken || !selectedFile) return;
    setIsLoading(true);
    setError(null);
    setNotice(null);
    try {
      const document = await uploadDocument(accessToken, selectedFile);
      setDocuments((current) => [document, ...current]);
      setSelectedFile(null);
      setNotice(`${document.filename} is indexed and ready to search.`);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to index that document.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleDelete(document: KnowledgeDocument) {
    if (!accessToken || !window.confirm(`Delete ${document.filename} and its indexed chunks?`)) return;
    setIsLoading(true);
    setError(null);
    try {
      await deleteDocument(accessToken, document.id);
      setDocuments((current) => current.filter((item) => item.id !== document.id));
      setNotice(`${document.filename} was deleted.`);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to delete that document.");
    } finally {
      setIsLoading(false);
    }
  }

  if (isAuthLoading) {
    return <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">Checking your session...</main>;
  }

  if (!user || !accessToken) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 px-6 py-12">
        <div className="rounded-3xl border border-slate-200 bg-white p-8 text-center shadow-panel">
          <p className="text-sm text-slate-500">Sign in to manage your knowledge base.</p>
          <Link href="/login" className="mt-5 inline-flex rounded-xl bg-ink px-5 py-3 text-sm font-semibold text-white">Sign in</Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_right,_#ddd6fe,_transparent_35%),#f8fafc] px-6 py-10">
      <div className="mx-auto max-w-5xl">
        <header className="flex items-center justify-between">
          <Link href="/" className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-ink font-bold text-white">N</span>
            <span className="font-semibold tracking-tight text-ink">NOVA</span>
          </Link>
          <nav className="flex items-center gap-4 text-sm font-semibold text-slate-500">
            <Link href="/voice" className="hover:text-ink">Voice Workspace</Link>
            <Link href="/" className="hover:text-ink">Home</Link>
          </nav>
        </header>

        <section className="mt-16 max-w-3xl">
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-accent">Personal knowledge</p>
          <h1 className="mt-4 text-5xl font-semibold tracking-tight text-ink">Knowledge Base</h1>
          <p className="mt-5 text-lg leading-8 text-slate-500">
            Upload documents for grounded answers with source citations. Your indexed files are private to your account.
          </p>
        </section>

        <section className="mt-10 rounded-3xl border border-slate-200 bg-white p-6 shadow-panel sm:p-8">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-ink">Add a document</h2>
              <p className="mt-1 text-sm text-slate-500">PDF, TXT, DOCX, or Markdown. Maximum size: 10 MB.</p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <input
                type="file"
                accept={ACCEPTED_TYPES}
                onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
                className="block max-w-xs text-sm text-slate-500 file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-50 file:px-3 file:py-2 file:font-semibold file:text-indigo-700"
              />
              <button
                onClick={() => void handleUpload()}
                disabled={!selectedFile || isLoading}
                className="rounded-xl bg-ink px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isLoading ? "Indexing..." : "Upload & index"}
              </button>
            </div>
          </div>
          {notice && <p className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{notice}</p>}
          {error && <p className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
        </section>

        <section className="mt-8 rounded-3xl border border-slate-200 bg-white p-6 shadow-panel sm:p-8">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-ink">Indexed documents</h2>
              <p className="mt-1 text-sm text-slate-500">{documents.length} document{documents.length === 1 ? "" : "s"} available to NOVA.</p>
            </div>
            <button onClick={() => void loadDocuments()} className="text-sm font-semibold text-accent hover:text-indigo-700">Refresh</button>
          </div>

          {documents.length === 0 ? (
            <p className="mt-8 rounded-2xl bg-slate-50 px-5 py-8 text-center text-sm text-slate-500">No documents indexed yet.</p>
          ) : (
            <div className="mt-6 divide-y divide-slate-100">
              {documents.map((document) => (
                <div key={document.id} className="flex flex-col gap-4 py-5 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="font-semibold text-ink">{document.filename}</p>
                    <p className="mt-1 text-sm text-slate-500">{document.chunk_count} searchable chunk{document.chunk_count === 1 ? "" : "s"} · {document.status}</p>
                  </div>
                  <button onClick={() => void handleDelete(document)} disabled={isLoading} className="self-start rounded-xl border border-red-200 px-4 py-2 text-sm font-semibold text-red-600 hover:bg-red-50 disabled:opacity-50 sm:self-auto">Delete</button>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
