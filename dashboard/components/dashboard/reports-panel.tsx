"use client";

import React, { useState } from "react";
import {
  AlertTriangle, BarChart3, Download, Hash, Link2, Loader2, Mic, Shield,
  ShieldAlert, Ticket, TrendingUp, UserCheck, Users, Webhook,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type ReportId =
  | "security-score" | "automod-recommendations" | "staff-permissions"
  | "role-risk" | "channel-risk" | "webhook-risk" | "ticket-load"
  | "invite-growth" | "member-retention" | "voice-analytics";

const REPORTS: Array<{ id: ReportId; label: string; desc: string; icon: any; group: string }> = [
  { id: "security-score", label: "Security Score", desc: "Rates every server 0-100 and lists what is missing.", icon: Shield, group: "Security" },
  { id: "automod-recommendations", label: "Automod Gaps", desc: "Automod modules that are not configured yet.", icon: ShieldAlert, group: "Security" },
  { id: "role-risk", label: "Role Risk", desc: "Roles with administrator or management permissions.", icon: UserCheck, group: "Security" },
  { id: "channel-risk", label: "Channel Risk", desc: "Channels everyone can write in.", icon: Hash, group: "Security" },
  { id: "webhook-risk", label: "Webhook Risk", desc: "Servers with an unusual number of webhooks.", icon: Webhook, group: "Security" },
  { id: "staff-permissions", label: "Staff Review", desc: "Members holding dangerous permissions.", icon: Users, group: "Security" },
  { id: "invite-growth", label: "Invite Growth", desc: "Invite performance per server.", icon: Link2, group: "Growth" },
  { id: "member-retention", label: "Retention", desc: "How many invited members stayed.", icon: TrendingUp, group: "Growth" },
  { id: "ticket-load", label: "Ticket Load", desc: "How open tickets are spread across staff.", icon: Ticket, group: "Operations" },
  { id: "voice-analytics", label: "Voice Activity", desc: "Time spent in voice channels per server.", icon: Mic, group: "Operations" },
];

const GROUPS = ["Security", "Growth", "Operations"] as const;

function scoreColor(score: number) {
  if (score >= 80) return "text-emerald-400";
  if (score >= 50) return "text-amber-400";
  return "text-red-400";
}

function scoreBar(score: number) {
  if (score >= 80) return "bg-emerald-400";
  if (score >= 50) return "bg-amber-400";
  return "bg-red-400";
}

export function ReportsPanel() {
  const [active, setActive] = useState<ReportId | null>(null);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const run = async (id: ReportId) => {
    setActive(id);
    setLoading(true);
    setData(null);
    try {
      const result = await api.getAdminReport(id);
      setData(result);
    } catch (err: any) {
      toast.error(err?.message || "Report failed.");
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  const exportReport = async () => {
    if (!active) return;
    try {
      const result = await api.getAdminReport(active);
      const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${active}-report.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Report downloaded.");
    } catch (err: any) {
      toast.error(err?.message || "Export failed.");
    }
  };

  return (
    <section className="space-y-6">
      <div className="glass border border-white/5 rounded-[2rem] p-8">
        <div className="flex items-center gap-4">
          <div className="h-12 w-12 rounded-2xl bg-primary/15 border border-primary/25 flex items-center justify-center">
            <BarChart3 className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h3 className="text-xl font-black text-white">Reports</h3>
            <p className="text-sm text-slate-400 mt-1">
              Analytics across every server the bot is in.
            </p>
          </div>
        </div>
      </div>

      {GROUPS.map((group) => (
        <div key={group} className="space-y-3">
          <p className="text-[10px] font-black uppercase tracking-[0.3em] text-slate-600 px-1">
            {group}
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {REPORTS.filter((r) => r.group === group).map((report) => (
              <button
                key={report.id}
                onClick={() => run(report.id)}
                disabled={loading}
                className={cn(
                  "text-left bg-[#10233f] border rounded-3xl p-5 transition-all disabled:opacity-50",
                  active === report.id
                    ? "border-primary/50 bg-primary/5"
                    : "border-slate-800 hover:border-primary/30"
                )}
              >
                <report.icon className="h-5 w-5 text-primary mb-3" />
                <h4 className="font-black text-white text-sm">{report.label}</h4>
                <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">{report.desc}</p>
              </button>
            ))}
          </div>
        </div>
      ))}

      {loading && (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
        </div>
      )}

      {data && !loading && (
        <div className="bg-[#10233f] border border-slate-800 rounded-3xl overflow-hidden">
          <div className="p-6 border-b border-white/5 flex items-center justify-between gap-4 flex-wrap">
            <h4 className="font-black text-white">
              {REPORTS.find((r) => r.id === active)?.label}
            </h4>
            <button
              onClick={exportReport}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06] transition-all text-xs font-black uppercase tracking-widest text-slate-400"
            >
              <Download className="h-3.5 w-3.5" />
              JSON
            </button>
          </div>

          <div className="p-6">
            <ReportBody id={active!} data={data} />
          </div>
        </div>
      )}
    </section>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="text-sm text-slate-500 py-6 text-center">{text}</p>;
}

function ReportBody({ id, data }: { id: ReportId; data: any }) {
  if (data.error) {
    return (
      <div className="flex gap-3 text-amber-300 text-sm">
        <AlertTriangle className="h-5 w-5 shrink-0" />
        {data.error}
      </div>
    );
  }

  // ── Security score ──────────────────────────────────────────────────────
  if (id === "security-score") {
    const guilds = data.guilds || [];
    if (!guilds.length) return <Empty text="No servers found." />;
    return (
      <div className="space-y-3">
        {guilds.map((g: any) => (
          <div key={g.guild_id} className="bg-white/[0.02] border border-white/5 rounded-2xl p-5">
            <div className="flex items-center justify-between gap-4 mb-3">
              <p className="font-bold text-white truncate">{g.guild_name}</p>
              <span className={cn("text-2xl font-black shrink-0", scoreColor(g.score))}>
                {g.score}
                <span className="text-xs text-slate-600">/100</span>
              </span>
            </div>
            <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
              <div
                className={cn("h-full rounded-full transition-all", scoreBar(g.score))}
                style={{ width: `${g.score}%` }}
              />
            </div>
            {g.issues?.length > 0 && (
              <ul className="mt-3 space-y-1">
                {g.issues.map((issue: string) => (
                  <li key={issue} className="text-xs text-slate-400 flex gap-2">
                    <span className="text-amber-400">•</span>
                    {issue}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    );
  }

  // ── Automod gaps ────────────────────────────────────────────────────────
  if (id === "automod-recommendations") {
    const guilds = data.guilds || [];
    if (!guilds.length) return <Empty text="Every server has its automod modules configured." />;
    return (
      <div className="space-y-3">
        {guilds.map((g: any) => (
          <div key={g.guild_id} className="bg-white/[0.02] border border-white/5 rounded-2xl p-5">
            <p className="font-bold text-white">{g.guild_name}</p>
            <div className="flex flex-wrap gap-1.5 mt-3">
              {g.missing_modules.map((m: string) => (
                <span
                  key={m}
                  className="text-[10px] font-black uppercase tracking-wider px-2 py-1 rounded-lg bg-amber-400/10 text-amber-400 border border-amber-400/20"
                >
                  {m}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  // ── Staff review ────────────────────────────────────────────────────────
  if (id === "staff-permissions") {
    const guilds = data.guilds || [];
    if (!guilds.length) return <Empty text="No staff members found." />;
    return (
      <div className="space-y-3">
        {guilds.map((g: any) => (
          <div key={g.guild_id} className="bg-white/[0.02] border border-white/5 rounded-2xl p-5">
            <div className="flex items-center justify-between gap-4">
              <p className="font-bold text-white truncate">{g.guild_name}</p>
              <span className="text-xs font-black text-primary shrink-0">
                {g.staff_count} staff
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5 mt-3">
              {g.members.map((m: any) => (
                <span
                  key={m.id}
                  className={cn(
                    "text-[10px] font-bold px-2 py-1 rounded-lg border",
                    m.level === "administrator"
                      ? "bg-red-400/10 text-red-400 border-red-400/20"
                      : "bg-white/[0.04] text-slate-400 border-white/5"
                  )}
                >
                  {m.name}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  // ── Role / channel risk ─────────────────────────────────────────────────
  if (id === "role-risk" || id === "channel-risk") {
    const guilds = data.guilds || [];
    if (!guilds.length) return <Empty text="Nothing flagged." />;
    return (
      <div className="space-y-3">
        {guilds.map((g: any) => (
          <div key={g.guild_id} className="bg-white/[0.02] border border-white/5 rounded-2xl p-5">
            <div className="flex items-center justify-between gap-4">
              <p className="font-bold text-white truncate">{g.guild_name}</p>
              {g.open_channel_count !== undefined && (
                <span className="text-xs font-black text-amber-400 shrink-0">
                  {g.open_channel_count} open
                </span>
              )}
            </div>
            <div className="flex flex-wrap gap-1.5 mt-3">
              {(g.roles || g.channels || []).map((item: any) => (
                <span
                  key={item.id}
                  className={cn(
                    "text-[10px] font-bold px-2 py-1 rounded-lg border",
                    item.risk === "administrator"
                      ? "bg-red-400/10 text-red-400 border-red-400/20"
                      : "bg-white/[0.04] text-slate-400 border-white/5"
                  )}
                >
                  {item.name}
                  {item.members > 0 && <span className="opacity-60"> · {item.members}</span>}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  // ── Webhook risk ────────────────────────────────────────────────────────
  if (id === "webhook-risk") {
    const guilds = data.guilds || [];
    if (!guilds.length) return <Empty text="No webhooks found (or the bot lacks Manage Webhooks)." />;
    return (
      <div className="space-y-2">
        <p className="text-xs text-slate-500 mb-4">
          Flagged above {data.threshold} webhooks.
        </p>
        {guilds.map((g: any) => (
          <div
            key={g.guild_id}
            className={cn(
              "flex items-center justify-between gap-4 p-4 rounded-2xl border",
              g.flagged
                ? "bg-amber-400/5 border-amber-400/20"
                : "bg-white/[0.02] border-white/5"
            )}
          >
            <p className="font-bold text-white truncate">{g.guild_name}</p>
            <span className={cn("text-sm font-black shrink-0", g.flagged ? "text-amber-400" : "text-slate-400")}>
              {g.webhook_count}
            </span>
          </div>
        ))}
      </div>
    );
  }

  // ── Ticket load ─────────────────────────────────────────────────────────
  if (id === "ticket-load") {
    const staff = data.staff || [];
    if (!staff.length) return <Empty text={data.note || "No claimed tickets."} />;
    const max = Math.max(...staff.map((s: any) => s.open_tickets), 1);
    return (
      <div className="space-y-2">
        {staff.map((s: any) => (
          <div key={s.staff_id} className="flex items-center gap-4">
            <code className="text-xs text-slate-400 font-mono w-44 truncate">{s.staff_id}</code>
            <div className="flex-1 h-6 bg-slate-800 rounded-lg overflow-hidden">
              <div
                className="h-full bg-primary rounded-lg flex items-center justify-end px-2"
                style={{ width: `${(s.open_tickets / max) * 100}%` }}
              >
                <span className="text-[10px] font-black text-white">{s.open_tickets}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  // ── Invite growth ───────────────────────────────────────────────────────
  if (id === "invite-growth") {
    const guilds = data.guilds || [];
    if (!guilds.length) return <Empty text="No invite data recorded yet." />;
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] font-black uppercase tracking-widest text-slate-600">
              <th className="text-left pb-3">Server</th>
              <th className="text-right pb-3">Total</th>
              <th className="text-right pb-3">Fake</th>
              <th className="text-right pb-3">Left</th>
              <th className="text-right pb-3">Inviters</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {guilds.map((g: any) => (
              <tr key={g.guild_id}>
                <td className="py-3 font-bold text-white truncate max-w-[200px]">{g.guild_name}</td>
                <td className="py-3 text-right text-emerald-400 font-bold">{g.total_invites}</td>
                <td className="py-3 text-right text-slate-500">{g.fake_invites}</td>
                <td className="py-3 text-right text-amber-400">{g.left}</td>
                <td className="py-3 text-right text-slate-400">{g.inviters}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  // ── Retention ───────────────────────────────────────────────────────────
  if (id === "member-retention") {
    const guilds = data.guilds || [];
    if (!guilds.length) return <Empty text={data.note || "No retention data yet."} />;
    return (
      <div className="space-y-3">
        {guilds.map((g: any) => (
          <div key={g.guild_id} className="bg-white/[0.02] border border-white/5 rounded-2xl p-5">
            <div className="flex items-center justify-between gap-4 mb-3">
              <p className="font-bold text-white truncate">{g.guild_name}</p>
              <span className={cn("text-lg font-black shrink-0", scoreColor(g.retention_percent))}>
                {g.retention_percent}%
              </span>
            </div>
            <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
              <div
                className={cn("h-full rounded-full", scoreBar(g.retention_percent))}
                style={{ width: `${g.retention_percent}%` }}
              />
            </div>
            <p className="text-xs text-slate-500 mt-2">
              {g.joined} joined · {g.left} left
            </p>
          </div>
        ))}
      </div>
    );
  }

  // ── Voice ───────────────────────────────────────────────────────────────
  if (id === "voice-analytics") {
    const guilds = data.guilds || [];
    if (!guilds.length) return <Empty text="No voice sessions recorded yet." />;
    return (
      <div className="space-y-2">
        {guilds.map((g: any) => (
          <div
            key={g.guild_id}
            className="flex items-center justify-between gap-4 p-4 bg-white/[0.02] border border-white/5 rounded-2xl"
          >
            <code className="text-xs text-slate-400 font-mono">{g.guild_id}</code>
            <span className="text-sm font-black text-primary">{g.total_minutes} min</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <pre className="text-xs text-slate-400 overflow-x-auto">{JSON.stringify(data, null, 2)}</pre>
  );
}
