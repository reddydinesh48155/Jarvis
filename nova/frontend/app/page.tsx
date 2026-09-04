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
          <p className="mt-6 text-lg leading-8 text-slate-500">Your NOVA identity is ready. This foundation keeps the access token in session state and the refresh token in a secure HTTP-only cookie.</p>
          <Link href="/voice" className="mt-8 inline-flex rounded-xl bg-ink px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800">Open Voice Workspace</Link>
        </section>
      </div>
    </main>
  );
}
