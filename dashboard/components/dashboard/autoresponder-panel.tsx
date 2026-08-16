"use client";

import React, { useEffect, useState } from "react";
import { Loader2, MessageSquare, Plus, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { EmojiText } from "@/components/dashboard/emoji-field";

const INPUT =
  "w-full bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary";

export function AutoresponderPanel({ guildId }: { guildId: string }) {
  const [items, setItems] = useState<Array<{ trigger: string; response: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [trigger, setTrigger] = useState("");
  const [response, setResponse] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.getAutoresponders(guildId);
      setItems(data.responses || []);
    } catch (err: any) {
      toast.error(err?.message || "Could not load autoresponders.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId]);

  const save = async () => {
    if (!trigger.trim()) return toast.error("Enter a trigger word.");
    if (!response.trim()) return toast.error("Enter the reply.");
    setBusy(true);
    try {
      await api.saveAutoresponder(guildId, trigger.trim(), response.trim());
      toast.success("Saved.");
      setTrigger("");
      setResponse("");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Could not save.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (t: string) => {
    setBusy(true);
    try {
      await api.deleteAutoresponder(guildId, t);
      toast.success("Deleted.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Could not delete.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-6">
      <div className="bg-[#131318] border border-slate-800 rounded-3xl p-8">
        <div className="flex items-center justify-between gap-4 mb-3 flex-wrap">
          <h3 className="font-black text-white flex items-center gap-2">
            <Plus className="h-5 w-5 text-primary" /> New autoresponder
          </h3>
          <button
            onClick={load}
            className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.06] transition-all"
          >
            <RefreshCw className={cn("h-4 w-4 text-primary", loading && "animate-spin")} />
          </button>
        </div>
        <p className="text-sm text-slate-400 mb-6">
          When somebody writes the trigger, the bot replies automatically.
        </p>

        <div className="space-y-4">
          <label className="block space-y-2">
            <span className="text-xs font-black uppercase tracking-widest text-slate-500">
              Trigger
            </span>
            <input
              value={trigger}
              onChange={(e) => setTrigger(e.target.value)}
              placeholder="hello"
              className={INPUT}
            />
          </label>

          <label className="block space-y-2">
            <span className="text-xs font-black uppercase tracking-widest text-slate-500">
              Reply
            </span>
            <EmojiText
              value={response}
              onChange={setResponse}
              placeholder="Hi there! How can we help?"
              rows={3}
              limit={2000}
              showCount
              onLimitReached={(cap) =>
                toast.error(`Eine Antwort darf höchstens ${cap} Zeichen haben.`)
              }
            />
          </label>
        </div>

        <button
          onClick={save}
          disabled={busy}
          className="mt-6 w-full py-4 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs shadow-xl shadow-primary/20 hover:brightness-110 disabled:opacity-50"
        >
          {busy ? "Working..." : "Save autoresponder"}
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-7 w-7 text-primary animate-spin opacity-40" />
        </div>
      ) : items.length === 0 ? (
        <p className="text-center text-slate-500 py-12">No autoresponders yet.</p>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <div
              key={item.trigger}
              className="bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6 flex items-start justify-between gap-4"
            >
              <div className="flex items-start gap-4 min-w-0">
                <MessageSquare className="h-5 w-5 text-primary shrink-0 mt-1" />
                <div className="min-w-0">
                  <code className="text-sm font-black text-white font-mono">
                    {item.trigger}
                  </code>
                  <p className="text-sm text-slate-400 mt-1.5 break-words">
                    {item.response}
                  </p>
                </div>
              </div>
              <button
                onClick={() => remove(item.trigger)}
                disabled={busy}
                className="p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-slate-500 hover:text-red-400 hover:bg-red-400/10 transition-all shrink-0 disabled:opacity-40"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
