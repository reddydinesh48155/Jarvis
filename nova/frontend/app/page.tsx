"use client";

import Link from "next/link";

import { useAuth } from "@/hooks/use-auth";

export default function HomePage() {
  const { user, isLoading, signOut } = useAuth();

  if (isLoading) {
    return <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">Loading NOVA...</main>;
  }

  if (!user) {
    return (
      <main className="min-h-screen bg-[radial-gradient(circle_at_top_right,_#ddd6fe,_transparent_35%),#f8fafc] px-6 py-10">
        <div className="mx-auto flex min-h-[80vh] max-w-5xl flex-col justify-center">
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-accent">NOVA / FOUNDATION</p>
          <h1 className="mt-5 max-w-3xl text-5xl font-semibold tracking-tight text-ink sm:text-7xl">A secure place to begin.</h1>
          <p className="mt-6 max-w-xl text-lg leading-8 text-slate-500">Part 1 established NOVA&apos;s identity layer. Sign in to open the LiveKit voice workspace; agents, memory, and retrieval arrive in later parts.</p>
          <div className="mt-9 flex flex-wrap gap-3">
            <Link href="/register" className="rounded-xl bg-ink px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800">Create account</Link>
            <Link href="/login" className="rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-ink hover:border-slate-300">Sign in</Link>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_right,_#ddd6fe,_transparent_35%),#f8fafc] px-6 py-10">
      <div className="mx-auto max-w-5xl">
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-ink font-bold text-white">N</span><span className="font-semibold tracking-tight text-ink">NOVA</span></div>
          <button onClick={() => void signOut()} className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-600 hover:border-slate-300">Sign out</button>
        </header>
        <section className="mt-24 max-w-2xl">
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-accent">Authenticated</p>
          <h1 className="mt-5 text-5xl font-semibold tracking-tight text-ink">Hello, {user.email}.</h1>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/voice" className="inline-flex rounded-xl bg-ink px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800">Open Voice Workspace</Link>
            <Link href="/knowledge" className="inline-flex rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-ink hover:border-slate-300">Manage Knowledge</Link>
            <Link href="/memory" className="inline-flex rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-ink hover:border-slate-300">Manage Memory</Link>
            <Link href="/security" className="inline-flex rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-ink hover:border-slate-300">Security &amp; Audit</Link>
          </div>
        </section>

        <section className="mt-14 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          <Link
            href="/voice"
            className="group rounded-3xl border border-slate-200 bg-white p-6 shadow-panel transition hover:border-slate-300 hover:shadow-md"
          >
            <span className="text-3xl">🎙️</span>
            <h2 className="mt-4 text-lg font-semibold text-ink group-hover:text-accent">Voice Workspace</h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-500">
              Real-time conversational AI with voice interaction, specialized agent routing, and tool execution.
            </p>
          </Link>

          <Link
            href="/knowledge"
            className="group rounded-3xl border border-slate-200 bg-white p-6 shadow-panel transition hover:border-slate-300 hover:shadow-md"
          >
            <span className="text-3xl">📚</span>
            <h2 className="mt-4 text-lg font-semibold text-ink group-hover:text-accent">Knowledge Base</h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-500">
              Upload and manage personal documents for grounded RAG answers with source citations.
            </p>
          </Link>

          <Link
            href="/memory"
            className="group rounded-3xl border border-slate-200 bg-white p-6 shadow-panel transition hover:border-slate-300 hover:shadow-md"
          >
            <span className="text-3xl">🧠</span>
            <h2 className="mt-4 text-lg font-semibold text-ink group-hover:text-accent">Memory Manager</h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-500">
              View, manage, and control what NOVA remembers about you
            </p>
          </Link>

          <Link
            href="/security"
            className="group rounded-3xl border border-slate-200 bg-white p-6 shadow-panel transition hover:border-slate-300 hover:shadow-md"
          >
            <span className="text-3xl">🔒</span>
            <h2 className="mt-4 text-lg font-semibold text-ink group-hover:text-accent">Security &amp; Audit</h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-500">
              View audit logs, tool executions, and security events (admin only).
            </p>
          </Link>
        </section>
      </div>
    </main>
  );
}
