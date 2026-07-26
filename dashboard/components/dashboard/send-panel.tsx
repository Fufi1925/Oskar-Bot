"use client";

import React, { useState } from "react";
import { CheckCircle2, ExternalLink, Loader2, Send } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Posts a module's panel into a Discord channel straight from the dashboard.
 *
 * Configuring verification or tickets used to only write to the database —
 * you still had to run a bot command by hand to get the actual message with
 * its buttons into a channel.
 */
export function SendPanel({
  guildId,
  kind,
  channels,
  defaultChannelId,
  title,
  description,
}: {
  guildId: string;
  kind: "verification" | "tickets";
  channels: Array<{ id: string; name: string }>;
  defaultChannelId?: string;
  title?: string;
  description?: string;
}) {
  const [channelId, setChannelId] = useState(defaultChannelId || "");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<{ url: string; channel: string } | null>(null);

  const send = async () => {
    if (!channelId) return toast.error("Pick a channel first.");
    setBusy(true);
    try {
      const result =
        kind === "verification"
          ? await api.sendVerificationPanel(guildId, channelId, title, description)
          : await api.sendTicketPanel(guildId, channelId);

      setSent({ url: result.url, channel: result.channel });
      toast.success(result.result);
    } catch (err: any) {
      // The API explains exactly what is missing (permissions, config, ...).
      toast.error(err?.message || "Could not send the panel.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bg-[#10233f] border border-primary/25 rounded-3xl p-6">
      <div className="flex items-center gap-3 mb-3">
        <Send className="h-5 w-5 text-primary" />
        <h4 className="font-black text-white">Post the panel</h4>
      </div>
      <p className="text-sm text-slate-400 mb-5 leading-relaxed">
        Saving above only stores the settings. This posts the actual message with its
        buttons into a channel.
      </p>

      <div className="flex flex-col sm:flex-row gap-3">
        <select
          value={channelId}
          onChange={(e) => setChannelId(e.target.value)}
          className="flex-1 appearance-none bg-[#0b1f3a] border border-white/10 rounded-2xl px-4 py-3 pr-9 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20fill%3D%22none%22%20viewBox%3D%220%200%2024%2024%22%20stroke%3D%22%2394a3b8%22%20stroke-width%3D%222%22%3E%3Cpath%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%20d%3D%22M19%209l-7%207-7-7%22/%3E%3C/svg%3E')] bg-[length:1.1rem] bg-[right_0.6rem_center] bg-no-repeat cursor-pointer"
        >
          <option value="">Select a channel...</option>
          {channels.map((c) => (
            <option key={c.id} value={c.id}>
              #{c.name}
            </option>
          ))}
        </select>

        <button
          onClick={send}
          disabled={busy || !channelId}
          className="px-8 py-3 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs shadow-xl shadow-primary/20 hover:brightness-110 disabled:opacity-40 flex items-center justify-center gap-2 shrink-0"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          {busy ? "Sending..." : "Send"}
        </button>
      </div>

      {sent && (
        <div className="mt-4 flex items-center gap-3 p-4 bg-emerald-500/10 border border-emerald-500/25 rounded-2xl">
          <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
          <p className="text-sm text-emerald-200 flex-1">
            Posted in #{sent.channel}.
          </p>
          <a
            href={sent.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-xs font-black uppercase tracking-widest text-emerald-400 hover:text-emerald-300"
          >
            Open <ExternalLink className="h-3 w-3" />
          </a>
        </div>
      )}
    </div>
  );
}
