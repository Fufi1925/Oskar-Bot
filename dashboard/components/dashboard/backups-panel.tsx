"use client";

import React, { useEffect, useState } from "react";
import {
  AlertTriangle, Database, Download, FileJson, HardDrive, Loader2, Plus, RefreshCw,
  RotateCcw, Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn, downloadFile } from "@/lib/utils";
import { ConfigTransferPanel } from "@/components/dashboard/config-transfer-panel";
import { FullBackupPanel } from "@/components/dashboard/full-backup-panel";
import { Select } from "@/components/ui/select";

interface Snapshot {
  name: string;
  created_at: number;
  file_count: number;
  size_bytes: number;
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatDate(unix: number) {
  if (!unix) return "unknown";
  return new Date(unix * 1000).toLocaleString();
}

export function BackupsPanel({
  guilds = [],
}: {
  guilds?: Array<{ id: string; name: string }>;
}) {
  // Per-server config export lives here too, next to the database backups.
  const [configGuild, setConfigGuild] = useState("");
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [live, setLive] = useState<{ file_count: number; size_bytes: number } | null>(null);
  const [schedulerOn, setSchedulerOn] = useState(false);
  const [scheduler, setScheduler] = useState<{
    interval_hours: number;
    keep: number;
    last_backup_at: number;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const data = await api.getBackups();
      setSnapshots(data.snapshots || []);
      setLive(data.live || null);
      setSchedulerOn(Boolean(data.scheduler_enabled));
      setScheduler(data.scheduler || null);
    } catch (err: any) {
      toast.error(err?.message || "Could not load the backups.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const createNow = async () => {
    setBusy(true);
    try {
      const result = await api.createBackup();
      toast.success(`Backup created: ${result.file_count} databases.`);
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Backup failed.");
    } finally {
      setBusy(false);
    }
  };

  const download = async (name: string | null) => {
    const url = name
      ? `/api/bot/admin/backups/${name}/download`
      : "/api/bot/admin/backups/live/download";
    try {
      const saved = await downloadFile(url, name ? `backup-${name}.zip` : "live.zip");
      toast.success(`Saved ${saved}`);
    } catch (err: any) {
      toast.error(err?.message || "Download failed.");
    }
  };

  const remove = async (name: string) => {
    setBusy(true);
    try {
      await api.deleteBackup(name);
      toast.success("Backup deleted.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Could not delete.");
    } finally {
      setBusy(false);
    }
  };

  const restore = async (name: string) => {
    // Overwrites the live databases, so make it a deliberate action.
    if (!confirm(
      `Restore snapshot "${name}"?\n\n` +
      "This overwrites the current databases. The present state is saved " +
      "as a pre-restore snapshot first, so it can be undone."
    )) return;

    setBusy(true);
    try {
      const res = await api.restoreBackup(name);
      toast.success(`Restored ${res.restored} databases.`);
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Restore failed.");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  return (
    <section className="space-y-6">
      <div className="glass border border-white/5 rounded-[2rem] p-5 sm:p-8">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <div className="h-12 w-12 rounded-2xl bg-primary/15 border border-primary/25 flex items-center justify-center">
              <Database className="h-6 w-6 text-primary" />
            </div>
            <div>
              <h3 className="text-xl font-black text-white">Backups</h3>
              <p className="text-sm text-slate-400 mt-1">
                {snapshots.length} Sicherungen · automatisch{" "}
                <span className={schedulerOn ? "text-emerald-400" : "text-slate-500"}>
                  {schedulerOn ? "an" : "aus"}
                </span>
                {schedulerOn && scheduler && (
                  <>
                    {" "}
                    · alle {scheduler.interval_hours} h, {scheduler.keep}{" "}
                    {scheduler.keep === 1 ? "wird behalten" : "werden behalten"}
                  </>
                )}
              </p>
              {schedulerOn && scheduler?.last_backup_at ? (
                <p className="text-xs text-slate-500 mt-0.5">
                  Letzte automatische Sicherung:{" "}
                  {formatDate(scheduler.last_backup_at)}
                </p>
              ) : null}
              {/* Worth saying, because keeping only one snapshot sounds
                  riskier than it is: the old one is only deleted once
                  the new one has been read back successfully. */}
              {schedulerOn && scheduler?.keep === 1 ? (
                <p className="text-xs text-slate-500 mt-0.5">
                  Die alte Sicherung wird erst gelöscht, wenn die neue
                  geprüft ist — schlägt sie fehl, bleibt die alte erhalten.
                </p>
              ) : null}
            </div>
          </div>

          <div className="flex gap-2">
            <button
              onClick={createNow}
              disabled={busy}
              className="flex items-center gap-2 px-5 py-3 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs hover:brightness-110 disabled:opacity-50"
            >
              <Plus className="h-4 w-4" />
              Backup now
            </button>
            <button
              onClick={load}
              className="p-3 rounded-2xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06] transition-all"
            >
              <RefreshCw className={cn("h-4 w-4 text-primary", busy && "animate-spin")} />
            </button>
          </div>
        </div>
      </div>

      {/* This is the important part — people lose data to this. */}
      <div className="bg-amber-500/10 border border-amber-500/30 rounded-3xl p-4 sm:p-6 flex gap-4">
        <AlertTriangle className="h-6 w-6 text-amber-400 shrink-0" />
        <div>
          <h4 className="font-black text-white">Railway wipes these on redeploy</h4>
          <p className="text-sm text-amber-200/80 mt-1 leading-relaxed">
            The container filesystem is ephemeral. Every deploy, restart or crash recycles
            it — including the live databases and every snapshot listed here. Download
            anything you want to keep, or attach a Railway volume mounted at{" "}
            <code className="px-1.5 py-0.5 rounded bg-black/20 font-mono text-xs">/app/bot/db</code>{" "}
            to make storage persistent.
          </p>
        </div>
      </div>

      {/* The one most people want: everything in a single file. */}
      <FullBackupPanel />

      {/* Still useful for cloning one server's setup onto another. */}
      <div className="bg-[#131318] border border-primary/25 rounded-3xl p-8 border-glow-card">
        <div className="flex items-center gap-3 mb-3">
          <FileJson className="h-5 w-5 text-primary" />
          <h4 className="font-black text-white">Single server</h4>
        </div>
        <p className="text-sm text-slate-400 mb-5 leading-relaxed">
          Only need one server? Export its settings on their own — handy for copying a
          setup onto another server. For a full backup use{" "}
          <span className="text-slate-300 font-bold">Complete backup</span> above.
        </p>

        <div className="max-w-md">
          <span className="text-xs font-black uppercase tracking-widest text-slate-500">
            Server
          </span>
          <div className="mt-2">
            <Select
              value={configGuild}
              onValueChange={setConfigGuild}
              options={guilds.map((g) => ({ value: String(g.id), label: `${g.name} (${g.id})` }))}
              placeholder="Select server"
            />
          </div>
        </div>

        {configGuild && (
          <div className="mt-6">
            <ConfigTransferPanel
              guildId={configGuild}
              guildName={guilds.find((g) => String(g.id) === configGuild)?.name}
            />
          </div>
        )}
      </div>

      {live && (
        <div className="bg-[#131318] border border-primary/25 rounded-3xl p-4 sm:p-6 flex items-center justify-between gap-4 flex-wrap border-glow-card">
          <div className="flex items-center gap-4">
            <HardDrive className="h-5 w-5 text-primary" />
            <div>
              <p className="font-black text-white">Current databases</p>
              <p className="text-xs text-slate-500 mt-0.5">
                {live.file_count} files · {formatSize(live.size_bytes)}
              </p>
            </div>
          </div>
          <button
            onClick={() => download(null)}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 transition-all text-xs font-black uppercase tracking-widest"
          >
            <Download className="h-3.5 w-3.5" />
            Download
          </button>
        </div>
      )}

      <div className="space-y-3">
        {snapshots.length === 0 ? (
          <p className="text-center text-slate-500 py-12">
            {/* Read from the scheduler rather than written out: the
                interval was hard-coded here and still said "6 hours"
                long after it had been changed. */}
            Noch keine Sicherung. Die automatische läuft
            {scheduler ? ` alle ${scheduler.interval_hours} h` : " regelmäßig"}
            {" "}— oder jetzt eine anlegen.
          </p>
        ) : (
          snapshots.map((snapshot) => (
            <div
              key={snapshot.name}
              className="bg-[#131318] border border-slate-800 rounded-3xl p-5 flex items-center justify-between gap-4 flex-wrap border-glow-card"
            >
              <div className="min-w-0">
                <code className="font-black text-white font-mono text-sm">{snapshot.name}</code>
                <p className="text-xs text-slate-500 mt-1">
                  {formatDate(snapshot.created_at)} · {snapshot.file_count} files ·{" "}
                  {formatSize(snapshot.size_bytes)}
                </p>
              </div>

              <div className="flex gap-2 shrink-0">
                <button
                  onClick={() => restore(snapshot.name)}
                  disabled={busy}
                  className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-amber-400 hover:bg-amber-400/10 transition-all disabled:opacity-40"
                  title="Restore this snapshot"
                >
                  <RotateCcw className="h-4 w-4" />
                </button>
                <button
                  onClick={() => download(snapshot.name)}
                  className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-primary hover:bg-primary/10 transition-all"
                  title="Download as zip"
                >
                  <Download className="h-4 w-4" />
                </button>
                <button
                  onClick={() => remove(snapshot.name)}
                  disabled={busy}
                  className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-slate-400 hover:text-red-400 hover:bg-red-400/10 transition-all disabled:opacity-40"
                  title="Delete"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
