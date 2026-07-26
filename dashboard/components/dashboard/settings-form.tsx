/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║                                                                  ║
 * ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
 * ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
 * ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
 * ║                                                                  ║
 * ║           © 2026 University Bot Devs — All Rights Reserved               ║
 * ║                                                                  ║
 * ║   discord  ──  https://discord.gg/MG3rYnUZJV                      ║
 * ║   youtube  ──  https://youtube.com/@University BotDevs                   ║
 * ║   github   ──  https://github.com/University Bot                        ║
 * ║                                                                  ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

"use client";

import React, { useState } from "react";
import { Save, RefreshCcw, Command, Info, Trash2, MessageCircle, Volume2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

interface SettingsFormProps {
  initialPrefix: string;
  initialExtraSettings?: {
    delete_command_messages?: boolean;
    mention_prefix_response?: boolean;
    same_voice_only?: boolean;
  };
  guildId: string;
}

export function SettingsForm({ initialPrefix, initialExtraSettings, guildId }: SettingsFormProps) {
  const [prefix, setPrefix] = useState(initialPrefix);
  const [deleteCommandMessages, setDeleteCommandMessages] = useState(Boolean(initialExtraSettings?.delete_command_messages));
  const [mentionPrefixResponse, setMentionPrefixResponse] = useState(initialExtraSettings?.mention_prefix_response ?? true);
  const [sameVoiceOnly, setSameVoiceOnly] = useState(initialExtraSettings?.same_voice_only ?? true);
  const [saving, setSaving] = useState(false);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prefix || prefix.length > 10) {
      toast.error("Prefix must be between 1 and 10 characters.");
      return;
    }

    setSaving(true);
    const promise = Promise.all([
      api.updatePrefix(guildId, prefix),
      api.updateExtraSettings(guildId, {
        delete_command_messages: deleteCommandMessages,
        mention_prefix_response: mentionPrefixResponse,
        same_voice_only: sameVoiceOnly,
      }),
    ]);

    toast.promise(promise, {
      loading: "Updating settings...",
      success: "Settings updated successfully!",
      error: (err) => err.message || "Failed to update settings",
    });

    try {
      await promise;
    } catch (err: any) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const extraToggles = [
    {
      title: "Delete command messages",
      desc: "Automatically delete user command messages after execution.",
      icon: Trash2,
      checked: deleteCommandMessages,
      setChecked: setDeleteCommandMessages,
    },
    {
      title: "Mention prefix response",
      desc: "Reply with the configured prefix when somebody mentions the bot.",
      icon: MessageCircle,
      checked: mentionPrefixResponse,
      setChecked: setMentionPrefixResponse,
    },
    {
      title: "Same voice channel only",
      desc: "Music controls should only work for users in the same voice channel.",
      icon: Volume2,
      checked: sameVoiceOnly,
      setChecked: setSameVoiceOnly,
    },
  ];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <div className="lg:col-span-2 space-y-6">
        <div className="bg-[#10233f] border border-slate-800 rounded-3xl overflow-hidden shadow-xl shadow-black/20">
          <div className="p-8 space-y-8">
            <form onSubmit={handleSave} className="space-y-8">
              <div className="space-y-2">
                <label className="text-sm font-black uppercase text-slate-500 tracking-widest flex items-center gap-2">
                  <Command className="h-4 w-4" />
                  Command Prefix
                </label>
                <div className="relative group">
                  <Input
                    value={prefix}
                    onChange={(e) => setPrefix(e.target.value)}
                    placeholder="e.g. !, ?, >>"
                    maxLength={10}
                    className="text-lg font-bold pr-20 py-7"
                  />
                  <div className="absolute right-4 top-1/2 -translate-y-1/2 text-xs font-mono text-slate-600 group-focus-within:text-primary transition-colors">
                    {prefix.length}/10
                  </div>
                </div>
                <p className="text-xs text-slate-500 italic">This character triggers bot commands (e.g. {prefix || ">"}help)</p>
              </div>

              <div className="space-y-4">
                <h3 className="text-sm font-black uppercase text-slate-500 tracking-widest">Additional Functions</h3>
                {extraToggles.map((item) => (
                  <div key={item.title} className="flex items-center justify-between gap-4 bg-slate-900/40 border border-slate-800 rounded-2xl p-5">
                    <div className="flex items-start gap-4">
                      <div className="p-3 rounded-xl bg-primary/10 text-primary"><item.icon className="h-5 w-5" /></div>
                      <div>
                        <p className="font-bold text-white">{item.title}</p>
                        <p className="text-sm text-slate-500 mt-1">{item.desc}</p>
                      </div>
                    </div>
                    <Switch checked={item.checked} onCheckedChange={item.setChecked} />
                  </div>
                ))}
              </div>

              <Button type="submit" disabled={saving || !prefix} className="w-full h-14 text-base font-bold gap-2 shadow-primary/20">
                {saving ? <RefreshCcw className="h-5 w-5 animate-spin" /> : <Save className="h-5 w-5" />}
                {saving ? "Saving Changes..." : "Save Configuration"}
              </Button>
            </form>
          </div>

          <div className="bg-slate-800/30 px-8 py-4 border-t border-slate-800 flex items-center justify-between">
            <span className="text-xs text-slate-500 font-medium">Last synced: Just now</span>
            <button className="text-xs text-primary hover:underline font-bold">Refresh Cache</button>
          </div>
        </div>
      </div>

      <div className="space-y-6">
        <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-6 relative overflow-hidden group">
          <div className="absolute -right-4 -top-4 opacity-[0.03] group-hover:scale-110 transition-transform">
            <Info className="h-32 w-32 text-white" />
          </div>
          <h3 className="text-sm font-black uppercase text-slate-500 tracking-widest mb-4 flex items-center gap-2">
            <Info className="h-4 w-4" />
            Information
          </h3>
          <div className="space-y-4 text-sm leading-relaxed text-slate-400">
            <p>The <span className="text-white font-bold italic">Prefix</span> is a unique identifier that tells the bot to process text as a command.</p>
            <p>The three additional switches are stored per server and can be used by bot modules and future dashboard automation.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
