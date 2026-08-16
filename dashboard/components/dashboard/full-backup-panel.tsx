"use client";

import React, { useRef, useState } from "react";
import {
  AlertTriangle, CheckCircle2, Download, Globe, Loader2, Server, Upload,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn, downloadFile } from "@/lib/utils";

interface Preview {
  scope: string;
  exported_at: number;
  includes_user_data: boolean;
  modules: string[];
  global_tables: string[];
  guild_count: number;
  table_count: number;
  row_count: number;
  json_files: string[];
  missing_databases: string[];
}

function formatDate(unix: number) {
  if (!unix) return "unknown";
  return new Date(unix * 1000).toLocaleString();
}

/**
 * One backup for the whole bot.
 *
 * Exports every server's settings for every module plus the global tables
 * (dashboard team and roles, feature flags, bot settings, blacklist,
 * premium, announcements) into a single JSON file — no need to pick a
 * server or repeat the export for each one. Uploading the file puts
 * everything back.
 */
export function FullBackupPanel() {
  const [busy, setBusy] = useState(false);
  const [includeUserData, setIncludeUserData] = useState(false);
  const [merge, setMerge] = useState(false);
  const [includeGlobal, setIncludeGlobal] = useState(true);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [pending, setPending] = useState<any>(null);
  const [result, setResult] = useState<any>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const exportAll = async () => {
    setBusy(true);
    try {
      const name = await downloadFile(
        `/api/bot/admin/backups/export-all?include_user_data=${includeUserData}`,
        `full-backup-${Date.now()}.json`
      );
      toast.success(`Saved ${name} — every server in one file.`);
    } catch (err: any) {
      toast.error(err?.message || "Download failed.");
    } finally {
      setBusy(false);
    }
  };

  const onFile = async (file: File) => {
    setResult(null);
    setPreview(null);
    setPending(null);
    setBusy(true);

    try {
      const text = await file.text();
      let parsed: any;
      try {
        parsed = JSON.parse(text);
      } catch {
        throw new Error("That is not a valid JSON file.");
      }

      const info = await api.previewFullBackup(parsed);
      setPreview(info);
      setPending(parsed);
    } catch (err: any) {
      toast.error(err?.message || "Could not read the file.");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const confirmImport = async () => {
    if (!pending) return;
    setBusy(true);
    try {
      const res = await api.importFullBackup(pending, merge, includeGlobal);
      setResult(res);
      setPreview(null);
      setPending(null);
      toast.success(`Restored ${res.rows_written} entries.`);
    } catch (err: any) {
      toast.error(err?.message || "Import failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bg-[#131318] border border-primary/25 rounded-3xl p-8">
      <div className="flex items-center gap-3 mb-3">
        <Globe className="h-5 w-5 text-primary" />
        <h4 className="font-black text-white">Complete backup — everything at once</h4>
      </div>
      <p className="text-sm text-slate-400 mb-6 leading-relaxed">
        Every setting of every server, for every module, plus the global
        configuration: dashboard team and roles, feature flags, bot settings,
        blacklist, premium and announcements — and the config that lives
        outside the databases, like the join-DM templates. One file,
        one click, no going through the servers one by one.
      </p>

      {/* ── Export ───────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={exportAll}
          disabled={busy}
          className="flex items-center gap-2 px-5 py-3 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs hover:brightness-110 disabled:opacity-50 transition-all"
        >
          <Download className="h-4 w-4" />
          Download everything
        </button>

        <button
          onClick={() => fileRef.current?.click()}
          disabled={busy}
          className="flex items-center gap-2 px-5 py-3 rounded-2xl bg-white/[0.03] border border-white/10 text-slate-200 hover:bg-white/[0.07] disabled:opacity-50 transition-all font-black uppercase tracking-widest text-xs"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          Restore from file
        </button>

        <input
          ref={fileRef}
          type="file"
          accept="application/json,.json"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onFile(f);
          }}
        />
      </div>

      <label className="flex items-center gap-2.5 mt-4 cursor-pointer w-fit">
        <input
          type="checkbox"
          checked={includeUserData}
          onChange={(e) => setIncludeUserData(e.target.checked)}
          className="h-4 w-4 rounded accent-[var(--primary,#3b82f6)]"
        />
        <span className="text-xs text-slate-400">
          Include user data (XP, warnings, tickets, invites) — much larger file
        </span>
      </label>

      {/* ── Preview before writing ───────────────────────────── */}
      {preview && (
        <div className="mt-6 bg-black/20 border border-amber-500/30 rounded-2xl p-6">
          <div className="flex items-center gap-2.5 mb-4">
            <AlertTriangle className="h-5 w-5 text-amber-400" />
            <h5 className="font-black text-white">Check before restoring</h5>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-5">
            {[
              { label: "Servers", value: preview.guild_count, icon: Server },
              { label: "Tables", value: preview.table_count },
              { label: "Entries", value: preview.row_count },
              { label: "Modules", value: preview.modules.length },
            ].map((s) => (
              <div key={s.label}>
                <p className="text-2xl font-black text-white">{s.value}</p>
                <p className="text-[10px] uppercase tracking-widest text-slate-500 font-black mt-0.5">
                  {s.label}
                </p>
              </div>
            ))}
          </div>

          <p className="text-xs text-slate-500 mb-4">
            Created {formatDate(preview.exported_at)}
            {preview.includes_user_data && " · contains user data"}
          </p>

          {preview.modules.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-4">
              {preview.modules.map((m) => (
                <span
                  key={m}
                  className="px-2.5 py-1 rounded-lg bg-primary/10 border border-primary/20 text-[11px] text-primary font-bold"
                >
                  {m}
                </span>
              ))}
            </div>
          )}

          {preview.global_tables.length > 0 && (
            <p className="text-xs text-slate-400 mb-4">
              <span className="font-black text-slate-300">Global settings included:</span>{" "}
              {preview.global_tables.join(", ")}
            </p>
          )}

          {preview.json_files?.length > 0 && (
            <p className="text-xs text-slate-400 mb-4">
              <span className="font-black text-slate-300">Also included:</span>{" "}
              {preview.json_files.join(", ")}
            </p>
          )}

          {preview.missing_databases.length > 0 && (
            <p className="text-xs text-amber-300/90 mb-4">
              Skipped, because these do not exist here:{" "}
              {preview.missing_databases.join(", ")}
            </p>
          )}

          <div className="space-y-2.5 border-t border-white/5 pt-4">
            <label className="flex items-start gap-2.5 cursor-pointer">
              <input
                type="checkbox"
                checked={merge}
                onChange={(e) => setMerge(e.target.checked)}
                className="h-4 w-4 mt-0.5 rounded accent-[var(--primary,#3b82f6)]"
              />
              <span className="text-xs text-slate-400">
                <span className="font-black text-slate-300">Merge</span> — keep what is
                already configured and only add the entries from the file. Off means
                every affected table is replaced by the backup.
              </span>
            </label>

            <label className="flex items-start gap-2.5 cursor-pointer">
              <input
                type="checkbox"
                checked={includeGlobal}
                onChange={(e) => setIncludeGlobal(e.target.checked)}
                className="h-4 w-4 mt-0.5 rounded accent-[var(--primary,#3b82f6)]"
              />
              <span className="text-xs text-slate-400">
                <span className="font-black text-slate-300">Restore global settings</span>{" "}
                — dashboard team, feature flags, bot settings. Turn off to keep the
                current ones and only restore the servers.
              </span>
            </label>
          </div>

          <p className="text-[11px] text-slate-500 mt-4 leading-relaxed">
            A safety copy of the current state is saved automatically before anything
            is overwritten, so this can be undone.
          </p>

          <div className="flex gap-2 mt-5">
            <button
              onClick={confirmImport}
              disabled={busy}
              className="flex items-center gap-2 px-5 py-2.5 bg-amber-500 text-black rounded-xl font-black uppercase tracking-widest text-xs hover:brightness-110 disabled:opacity-50 transition-all"
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
              Restore now
            </button>
            <button
              onClick={() => {
                setPreview(null);
                setPending(null);
              }}
              className="px-5 py-2.5 rounded-xl bg-white/[0.03] border border-white/10 text-slate-300 hover:bg-white/[0.07] transition-all text-xs font-black uppercase tracking-widest"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* ── Result ───────────────────────────────────────────── */}
      {result && (
        <div className="mt-6 bg-emerald-500/10 border border-emerald-500/30 rounded-2xl p-6">
          <div className="flex items-center gap-2.5 mb-2">
            <CheckCircle2 className="h-5 w-5 text-emerald-400" />
            <h5 className="font-black text-white">Restored</h5>
          </div>
          <p className="text-sm text-emerald-200/80">
            {result.rows_written} entries written across {result.tables_written} tables
            {result.json_files_written?.length
              ? `, plus ${result.json_files_written.length} config files`
              : ""}
            .
          </p>
          {result.safety_backup?.name && (
            <p className="text-xs text-slate-400 mt-2">
              Previous state saved as{" "}
              <code className="px-1.5 py-0.5 rounded bg-black/30 font-mono">
                {result.safety_backup.name}
              </code>
            </p>
          )}
          {Array.isArray(result.skipped) && result.skipped.length > 0 && (
            <details className="mt-3">
              <summary className="text-xs text-slate-400 cursor-pointer hover:text-slate-300">
                {result.skipped.length} skipped
              </summary>
              <ul className="mt-2 space-y-1">
                {result.skipped.map((s: string, i: number) => (
                  <li key={i} className="text-[11px] text-slate-500 font-mono">
                    {s}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
