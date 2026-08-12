"use client";

import React, { useRef, useState } from "react";
import {
  AlertTriangle, CheckCircle2, Download, FileJson, Loader2, RotateCcw, Upload,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn, downloadFile } from "@/lib/utils";

interface Preview {
  source_guild_id: string;
  exported_at: number;
  includes_user_data: boolean;
  modules: string[];
  table_count: number;
  row_count: number;
  missing_databases: string[];
}

/**
 * Export and import a server's entire configuration as one JSON file.
 *
 * Backs up every module at once — welcome, automod, antinuke, leveling,
 * tickets, verification, roles, logging and the rest — and puts it all back
 * with a single upload.
 */
export function ConfigTransferPanel({ guildId, guildName }: { guildId: string; guildName?: string }) {
  const [busy, setBusy] = useState(false);
  const [includeUserData, setIncludeUserData] = useState(false);
  const [merge, setMerge] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [pending, setPending] = useState<any>(null);
  const [result, setResult] = useState<any>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const exportConfig = async () => {
    setBusy(true);
    try {
      const name = await downloadFile(
        `/api/bot/guilds/${guildId}/config/export?include_user_data=${includeUserData}`,
        `config-${guildId}.json`
      );
      toast.success(`Saved ${name}`);
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

    let parsed: any;
    try {
      parsed = JSON.parse(await file.text());
    } catch {
      toast.error("That is not a valid JSON file.");
      return;
    }

    setBusy(true);
    try {
      const info = await api.previewConfig(guildId, parsed);
      setPreview(info);
      setPending(parsed);
    } catch (err: any) {
      toast.error(err?.message || "This file cannot be imported.");
    } finally {
      setBusy(false);
    }
  };

  const applyImport = async () => {
    if (!pending) return;
    setBusy(true);
    try {
      const res = await api.importConfig(guildId, pending, merge);
      setResult(res);
      setPreview(null);
      setPending(null);
      if (fileRef.current) fileRef.current.value = "";
      toast.success(`${res.rows_written} settings restored.`);
    } catch (err: any) {
      toast.error(err?.message || "Import failed.");
    } finally {
      setBusy(false);
    }
  };

  const resetAll = async () => {
    setBusy(true);
    try {
      const res = await api.resetConfig(guildId);
      toast.success(`${res.rows_deleted} settings removed.`);
      setConfirmReset(false);
    } catch (err: any) {
      toast.error(err?.message || "Reset failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-6">
      <div className="glass border border-white/5 rounded-[2rem] p-5 sm:p-8">
        <div className="flex items-center gap-4">
          <div className="h-12 w-12 rounded-2xl bg-primary/15 border border-primary/25 flex items-center justify-center">
            <FileJson className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h3 className="text-xl font-black text-white">Backup &amp; Restore</h3>
            <p className="text-sm text-slate-400 mt-1">
              Every setting of {guildName || "this server"} in one file.
            </p>
          </div>
        </div>
      </div>

      {/* Export */}
      <div className="bg-[#131318] border border-slate-800 rounded-3xl p-8 border-glow-card">
        <h4 className="font-black text-white flex items-center gap-2 mb-3">
          <Download className="h-5 w-5 text-primary" /> Export
        </h4>
        <p className="text-sm text-slate-400 mb-5 leading-relaxed">
          Downloads one JSON file containing everything configured here: prefix, welcome
          messages, automod, anti-nuke, leveling, tickets, verification, all role systems,
          logging and every other module.
        </p>

        <label className="flex items-start gap-3 cursor-pointer mb-6">
          <input
            type="checkbox"
            checked={includeUserData}
            onChange={(e) => setIncludeUserData(e.target.checked)}
            className="accent-primary mt-0.5"
          />
          <span className="text-sm text-slate-300">
            Include member data
            <span className="block text-xs text-slate-500 mt-0.5">
              XP, warnings and ticket counts. Leave off when copying the setup to another
              server — that data belongs to this one.
            </span>
          </span>
        </label>

        <button
          onClick={exportConfig}
          className="w-full py-4 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs shadow-xl shadow-primary/20 hover:brightness-110 flex items-center justify-center gap-2"
        >
          <Download className="h-4 w-4" />
          Download configuration
        </button>
      </div>

      {/* Import */}
      <div className="bg-[#131318] border border-slate-800 rounded-3xl p-8 border-glow-card">
        <h4 className="font-black text-white flex items-center gap-2 mb-3">
          <Upload className="h-5 w-5 text-primary" /> Import
        </h4>
        <p className="text-sm text-slate-400 mb-5 leading-relaxed">
          Upload a file exported here or from another server. You get a summary first and
          nothing is written until you confirm.
        </p>

        <input
          ref={fileRef}
          type="file"
          accept="application/json,.json"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onFile(file);
          }}
          className="block w-full text-sm text-slate-400 file:mr-4 file:py-3 file:px-5 file:rounded-2xl file:border-0 file:bg-primary/15 file:text-primary file:font-black file:uppercase file:tracking-widest file:text-xs hover:file:bg-primary/25 file:cursor-pointer cursor-pointer"
        />

        {busy && !preview && (
          <div className="flex items-center gap-2 mt-4 text-sm text-slate-400">
            <Loader2 className="h-4 w-4 animate-spin" /> Reading file...
          </div>
        )}

        {preview && (
          <div className="mt-6 space-y-4">
            <div className="p-5 bg-white/[0.02] border border-white/5 rounded-2xl">
              <p className="text-xs font-black uppercase tracking-widest text-slate-500 mb-3">
                This file contains
              </p>
              <div className="flex flex-wrap gap-1.5 mb-4">
                {preview.modules.map((m) => (
                  <span
                    key={m}
                    className="text-[10px] font-bold px-2 py-1 rounded-lg bg-primary/10 text-primary border border-primary/20"
                  >
                    {m}
                  </span>
                ))}
              </div>
              <p className="text-sm text-slate-400">
                {preview.row_count} settings across {preview.table_count} modules
              </p>
              <p className="text-xs text-slate-600 mt-1">
                From server {preview.source_guild_id}
                {preview.source_guild_id !== guildId && (
                  <span className="text-amber-400"> — different server, will be cloned</span>
                )}
                {preview.exported_at > 0 && (
                  <> · {new Date(preview.exported_at * 1000).toLocaleString()}</>
                )}
              </p>

              {preview.includes_user_data && (
                <p className="text-xs text-amber-400 mt-2">
                  Contains member data (XP, warnings).
                </p>
              )}
              {preview.missing_databases.length > 0 && (
                <p className="text-xs text-amber-400 mt-2">
                  {preview.missing_databases.length} tables are unknown to this bot and will
                  be skipped.
                </p>
              )}
            </div>

            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={merge}
                onChange={(e) => setMerge(e.target.checked)}
                className="accent-primary mt-0.5"
              />
              <span className="text-sm text-slate-300">
                Merge instead of replace
                <span className="block text-xs text-slate-500 mt-0.5">
                  Off: current settings for the imported modules are cleared first — the
                  normal choice when restoring a backup. On: entries are added on top of
                  what is already there.
                </span>
              </span>
            </label>

            <div className="flex gap-3">
              <button
                onClick={applyImport}
                disabled={busy}
                className="flex-1 py-4 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs hover:brightness-110 disabled:opacity-50"
              >
                {busy ? "Applying..." : "Apply now"}
              </button>
              <button
                onClick={() => {
                  setPreview(null);
                  setPending(null);
                  if (fileRef.current) fileRef.current.value = "";
                }}
                className="px-6 py-4 rounded-2xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-white transition-all text-xs font-black uppercase tracking-widest"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {result && (
          <div className="mt-6 p-5 bg-emerald-500/10 border border-emerald-500/25 rounded-2xl">
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle2 className="h-5 w-5 text-emerald-400" />
              <p className="font-black text-white">Restored</p>
            </div>
            <p className="text-sm text-emerald-200/80">
              {result.rows_written} settings written across {result.tables_written} modules.
              The bot picked them up immediately.
            </p>
            {result.skipped?.length > 0 && (
              <details className="mt-3">
                <summary className="text-xs text-slate-400 cursor-pointer">
                  {result.skipped.length} skipped
                </summary>
                <ul className="mt-2 space-y-1">
                  {result.skipped.map((s: string) => (
                    <li key={s} className="text-[11px] text-slate-500 font-mono">{s}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}
      </div>

      {/* Reset */}
      <div className="bg-[#131318] border border-red-500/20 rounded-3xl p-8 border-glow-card">
        <h4 className="font-black text-white flex items-center gap-2 mb-3">
          <RotateCcw className="h-5 w-5 text-red-400" /> Reset
        </h4>
        <p className="text-sm text-slate-400 mb-5 leading-relaxed">
          Removes every setting for this server and starts from scratch. Member data such
          as XP and warnings is kept.
        </p>

        {confirmReset ? (
          <div className="space-y-4">
            <div className="flex gap-3 p-4 bg-red-500/10 border border-red-500/25 rounded-2xl">
              <AlertTriangle className="h-5 w-5 text-red-400 shrink-0" />
              <p className="text-sm text-red-200">
                This cannot be undone. Export a backup first if you might want it back.
              </p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={resetAll}
                disabled={busy}
                className="flex-1 py-4 bg-red-500/15 text-red-400 border border-red-500/30 rounded-2xl font-black uppercase tracking-widest text-xs hover:bg-red-500/25 disabled:opacity-50"
              >
                {busy ? "Resetting..." : "Yes, delete everything"}
              </button>
              <button
                onClick={() => setConfirmReset(false)}
                className="px-6 py-4 rounded-2xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-white transition-all text-xs font-black uppercase tracking-widest"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setConfirmReset(true)}
            className="w-full py-4 rounded-2xl bg-white/[0.03] border border-red-500/20 text-red-400/80 hover:text-red-400 hover:bg-red-500/10 transition-all font-black uppercase tracking-widest text-xs"
          >
            Reset all settings
          </button>
        )}
      </div>
    </section>
  );
}
