"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/hooks/use-auth";
import { clearAllMemories, deleteMemory, listMemories, updateMemorySettings } from "@/lib/api";
import type { Memory } from "@/types/memory";

const CATEGORY_STYLES: Record<string, string> = {
  preference: "bg-purple-50 text-purple-700 border-purple-200",
  fact: "bg-blue-50 text-blue-700 border-blue-200",
  project: "bg-emerald-50 text-emerald-700 border-emerald-200",
  instruction: "bg-amber-50 text-amber-700 border-amber-200",
  personal: "bg-rose-50 text-rose-700 border-rose-200",
};

export default function MemoryPage() {
  const { user, accessToken, isLoading: isAuthLoading } = useAuth();
  const [memories, setMemories] = useState<Memory[]>([]);
  const [memoryEnabled, setMemoryEnabled] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [isUpdatingSettings, setIsUpdatingSettings] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadMemories = useCallback(async () => {
    if (!accessToken) return;
    setIsLoading(true);
    try {
      const response = await listMemories(accessToken);
      setMemories(response.memories);
      setMemoryEnabled(response.memory_enabled);
      setError(null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to load memories.");
    } finally {
      setIsLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void loadMemories();
  }, [loadMemories]);

  async function handleToggleSettings() {
    if (!accessToken || isUpdatingSettings) return;
    const targetState = !memoryEnabled;
    setIsUpdatingSettings(true);
    setError(null);
    setNotice(null);
    try {
      const response = await updateMemorySettings(accessToken, targetState);
      setMemoryEnabled(response.memory_enabled);
      setNotice(response.memory_enabled ? "Memory enabled. NOVA will remember facts." : "Memory paused. NOVA will not store or recall facts.");
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Failed to update memory settings.");
    } finally {
      setIsUpdatingSettings(false);
    }
  }

  async function handleDeleteMemory(memoryId: string) {
    if (!accessToken || !window.confirm("Delete this memory?")) return;
    setIsLoading(true);
    setError(null);
    setNotice(null);
    try {
      await deleteMemory(accessToken, memoryId);
      setMemories((current) => current.filter((item) => item.id !== memoryId));
      setNotice("Memory removed.");
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to delete memory.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleClearAll() {
    if (!accessToken || !window.confirm("Are you sure you want to clear all stored memories? This cannot be undone.")) return;
    setIsLoading(true);
    setError(null);
    setNotice(null);
    try {
      await clearAllMemories(accessToken);
      setMemories([]);
      setNotice("All memories have been cleared.");
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to clear memories.");
    } finally {
      setIsLoading(false);
    }
  }

  function formatDate(dateStr: string | null) {
    if (!dateStr) return null;
    try {
      return new Date(dateStr).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    } catch {
      return dateStr;
    }
  }

  if (isAuthLoading) {
    return <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">Checking your session...</main>;
  }

  if (!user || !accessToken) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 px-6 py-12">
        <div className="rounded-3xl border border-slate-200 bg-white p-8 text-center shadow-panel">
          <p className="text-sm text-slate-500">Sign in to manage your memory settings.</p>
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
            <Link href="/knowledge" className="hover:text-ink">Knowledge</Link>
            <Link href="/" className="hover:text-ink">Home</Link>
          </nav>
        </header>

        <section className="mt-16 max-w-3xl">
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-accent">Personal Context</p>
          <h1 className="mt-4 text-5xl font-semibold tracking-tight text-ink">Memory Manager</h1>
          <p className="mt-5 text-lg leading-8 text-slate-500">
            View, manage, and control what NOVA remembers about you across voice sessions.
          </p>
        </section>

        {/* Settings Card */}
        <section className="mt-10 rounded-3xl border border-slate-200 bg-white p-6 shadow-panel sm:p-8">
          <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-ink">Memory Retention</h2>
              <p className="mt-1 text-sm text-slate-500">
                {memoryEnabled
                  ? "NOVA will extract and remember personal preferences, projects, and context."
                  : "Memory is disabled. NOVA will not form new memories or recall past context."}
              </p>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-sm font-medium text-slate-700">
                {memoryEnabled ? "Enabled" : "Disabled"}
              </span>
              <button
                type="button"
                role="switch"
                aria-checked={memoryEnabled}
                onClick={() => void handleToggleSettings()}
                disabled={isUpdatingSettings || isLoading}
                className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  memoryEnabled ? "bg-accent" : "bg-slate-300"
                } disabled:opacity-50`}
              >
                <span
                  aria-hidden="true"
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                    memoryEnabled ? "translate-x-5" : "translate-x-0"
                  }`}
                />
              </button>
            </div>
          </div>

          {notice && <p className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{notice}</p>}
          {error && <p className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
        </section>

        {/* Stored Memories List Card */}
        <section className="mt-8 rounded-3xl border border-slate-200 bg-white p-6 shadow-panel sm:p-8">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-ink">Stored Memories</h2>
              <p className="mt-1 text-sm text-slate-500">
                {memories.length} memor{memories.length === 1 ? "y" : "ies"} stored.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => void loadMemories()}
                disabled={isLoading}
                className="text-sm font-semibold text-accent hover:text-indigo-700 disabled:opacity-50"
              >
                Refresh
              </button>
              {memories.length > 0 && (
                <button
                  onClick={() => void handleClearAll()}
                  disabled={isLoading}
                  className="rounded-xl border border-red-200 px-3.5 py-1.5 text-sm font-semibold text-red-600 hover:bg-red-50 disabled:opacity-50"
                >
                  Clear all memories
                </button>
              )}
            </div>
          </div>

          {!memoryEnabled && (
            <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50/70 p-4 text-sm text-amber-800">
              ⚠️ Memory is currently disabled. NOVA will not recall these memories or store new ones until re-enabled.
            </div>
          )}

          {memories.length === 0 ? (
            <p className="mt-8 rounded-2xl bg-slate-50 px-5 py-8 text-center text-sm text-slate-500">
              No memories saved yet. Speak with NOVA in the voice workspace to start building context.
            </p>
          ) : (
            <div className="mt-6 divide-y divide-slate-100">
              {memories.map((memory) => {
                const badgeStyle = CATEGORY_STYLES[memory.category.toLowerCase()] || "bg-slate-50 text-slate-600 border-slate-200";
                const createdDate = formatDate(memory.created_at);
                const accessedDate = formatDate(memory.last_accessed_at);

                return (
                  <div key={memory.id} className="flex flex-col gap-4 py-5 sm:flex-row sm:items-start sm:justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2.5">
                        <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${badgeStyle}`}>
                          {memory.category}
                        </span>
                        {createdDate && (
                          <span className="text-xs text-slate-400">
                            Saved {createdDate}
                          </span>
                        )}
                        {accessedDate && (
                          <span className="text-xs text-slate-400">
                            · Recalled {accessedDate}
                          </span>
                        )}
                      </div>
                      <p className="mt-2 text-sm leading-relaxed text-slate-800">{memory.content}</p>
                    </div>
                    <button
                      onClick={() => void handleDeleteMemory(memory.id)}
                      disabled={isLoading}
                      className="self-start rounded-xl border border-red-200 px-3 py-1.5 text-xs font-semibold text-red-600 hover:bg-red-50 disabled:opacity-50 sm:self-auto"
                    >
                      Delete
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
