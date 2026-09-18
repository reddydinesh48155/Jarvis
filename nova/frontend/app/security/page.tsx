"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { useAuth } from "@/hooks/use-auth";
import { getAuditLogs } from "@/lib/api";
import type { AuditLogEntry } from "@/types/admin";

export default function SecurityPage() {
  const { user, accessToken, isLoading: isAuthLoading } = useAuth();
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filterTool, setFilterTool] = useState("");

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    getAuditLogs(accessToken, {
      limit: 50,
      tool_name: filterTool || undefined,
    })
      .then((data) => {
        setLogs(data.logs);
        setTotal(data.total);
        setError(null);
      })
      .catch((err) => {
        if (err?.status === 403) {
          setError("Admin access required. This page is only available to administrators.");
        } else {
          setError(err?.message ?? "Failed to load audit logs.");
        }
      })
      .finally(() => setLoading(false));
  }, [accessToken, filterTool]);

  if (isAuthLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">
        Loading...
      </main>
    );
  }

  if (!user || !accessToken) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 text-sm text-slate-500">
        <p>Please sign in to continue.</p>
        <Link href="/login" className="text-accent underline">Sign in</Link>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_right,_#ddd6fe,_transparent_35%),#f8fafc] px-6 py-10">
      <div className="mx-auto max-w-6xl">
        <header className="mb-8 flex items-center justify-between">
          <div>
            <Link href="/" className="text-sm text-slate-500 hover:text-slate-700">
              ← Back to Home
            </Link>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-ink">
              🔒 Security &amp; Audit Logs
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Admin-only view of tool executions, confirmations, and security events.
            </p>
          </div>
        </header>

        {error ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center">
            <p className="text-sm font-medium text-red-700">{error}</p>
          </div>
        ) : loading ? (
          <div className="flex items-center justify-center py-16 text-sm text-slate-500">
            Loading audit logs...
          </div>
        ) : (
          <>
            {/* Filter */}
            <div className="mb-6 flex items-center gap-4">
              <input
                type="text"
                placeholder="Filter by tool name..."
                value={filterTool}
                onChange={(e) => setFilterTool(e.target.value)}
                className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm text-ink outline-none focus:border-accent focus:ring-1 focus:ring-accent"
              />
              <span className="text-sm text-slate-500">{total} total entries</span>
            </div>

            {/* Table */}
            {logs.length === 0 ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center">
                <p className="text-lg font-medium text-slate-400">No audit logs yet</p>
                <p className="mt-2 text-sm text-slate-400">
                  Tool executions and security events will appear here.
                </p>
              </div>
            ) : (
              <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-panel">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-slate-200 bg-slate-50">
                    <tr>
                      <th className="px-4 py-3 font-medium text-slate-600">Tool</th>
                      <th className="px-4 py-3 font-medium text-slate-600">Risk</th>
                      <th className="px-4 py-3 font-medium text-slate-600">Status</th>
                      <th className="px-4 py-3 font-medium text-slate-600">Confirmed</th>
                      <th className="px-4 py-3 font-medium text-slate-600">User</th>
                      <th className="px-4 py-3 font-medium text-slate-600">Time (ms)</th>
                      <th className="px-4 py-3 font-medium text-slate-600">Timestamp</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map((log) => {
                      const rowColor = log.success
                        ? "bg-green-50/50"
                        : log.requires_confirmation
                          ? "bg-amber-50/50"
                          : "bg-red-50/50";
                      const riskColor =
                        log.permission_level === "HIGH"
                          ? "text-red-600 bg-red-100"
                          : log.permission_level === "MEDIUM"
                            ? "text-amber-600 bg-amber-100"
                            : "text-green-600 bg-green-100";

                      return (
                        <tr key={log.id} className={`border-b border-slate-100 ${rowColor}`}>
                          <td className="px-4 py-3 font-mono text-xs">{log.tool_name}</td>
                          <td className="px-4 py-3">
                            <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${riskColor}`}>
                              {log.permission_level}
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            {log.success ? (
                              <span className="text-green-600">✓ Success</span>
                            ) : log.requires_confirmation ? (
                              <span className="text-amber-600">⏳ Awaiting</span>
                            ) : (
                              <span className="text-red-600" title={log.error_message ?? ""}>
                                ✗ Failed
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            {log.confirmed ? "✓" : log.requires_confirmation ? "Pending" : "—"}
                          </td>
                          <td className="px-4 py-3 text-xs text-slate-500">
                            {log.user_id ? log.user_id.slice(0, 8) + "…" : "—"}
                          </td>
                          <td className="px-4 py-3 text-xs text-slate-500">
                            {log.execution_time_ms != null ? log.execution_time_ms.toFixed(1) : "—"}
                          </td>
                          <td className="px-4 py-3 text-xs text-slate-500">
                            {(log.created_at || log.timestamp)
                              ? new Date(log.created_at || log.timestamp || "").toLocaleString()
                              : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}
