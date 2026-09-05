"use client";

import React, { useEffect, useState } from "react";
import { Bot, Loader2, Save, Users, UserRound, Volume2 } from "lucide-react";
import { toast } from "sonner";

import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";

const CARD = "rounded-3xl border border-slate-800 bg-[#131318]";

type Kind = "humans" | "bots" | "total";
type Form = Record<`${Kind}_enabled`, boolean>;

const ITEMS: Array<{
  kind: Kind;
  title: string;
  description: string;
  preview: (count: number) => string;
  icon: typeof Users;
  color: string;
}> = [
  {
    kind: "humans",
    title: "Nutzer ohne Bots",
    description: "Zählt ausschließlich echte Mitglieder.",
    preview: (count) => `👤 Nutzer: ${count}`,
    icon: UserRound,
    color: "text-sky-400",
  },
  {
    kind: "bots",
    title: "Nur Bots",
    description: "Zeigt, wie viele Bot-Konten auf dem Server sind.",
    preview: (count) => `🤖 Bots: ${count}`,
    icon: Bot,
    color: "text-violet-400",
  },
  {
    kind: "total",
    title: "Alle Mitglieder",
    description: "Menschen und Bots zusammen.",
    preview: (count) => `👥 Mitglieder: ${count}`,
    icon: Users,
    color: "text-emerald-400",
  },
];

export function ServerStatsPanel({ guildId }: { guildId: string }) {
  const [data, setData] = useState<any>(null);
  const [form, setForm] = useState<Form>({
    humans_enabled: false,
    bots_enabled: false,
    total_enabled: false,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getServerStats(guildId)
      .then((answer) => {
        if (cancelled) return;
        setData(answer);
        setForm({
          humans_enabled: Boolean(answer.humans_enabled),
          bots_enabled: Boolean(answer.bots_enabled),
          total_enabled: Boolean(answer.total_enabled),
        });
      })
      .catch((error) => {
        if (!cancelled)
          toast.error(error?.message || "Server-Stats konnten nicht geladen werden.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [guildId]);

  const save = async () => {
    setSaving(true);
    try {
      const answer = await api.updateServerStats(guildId, form);
      setData(answer);
      setForm({
        humans_enabled: Boolean(answer.humans_enabled),
        bots_enabled: Boolean(answer.bots_enabled),
        total_enabled: Boolean(answer.total_enabled),
      });
      toast.success("Server-Stats wurden aktualisiert.");
    } catch (error: any) {
      toast.error(error?.message || "Server-Stats konnten nicht gespeichert werden.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className={`${CARD} flex min-h-48 items-center justify-center`}>
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  const changed = data && ITEMS.some(({ kind }) =>
    Boolean(data[`${kind}_enabled`]) !== form[`${kind}_enabled`]
  );

  return (
    <div className="space-y-5">
      {data?.warning && (
        <div className="rounded-2xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          {data.warning} Ohne dieses Recht kann der Bot keine Statistikkanäle anlegen oder umbenennen.
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        {ITEMS.map(({ kind, title, description, preview, icon: Icon, color }) => {
          const enabledKey = `${kind}_enabled` as keyof Form;
          const count = Number(data?.counts?.[kind] || 0);
          const channel = data?.channels?.[kind];
          return (
            <div key={kind} className={`${CARD} overflow-hidden p-5`}>
              <div className="flex items-start justify-between gap-4">
                <div className="flex min-w-0 gap-3">
                  <div className="rounded-xl border border-slate-800 bg-[#0e0e12] p-2.5">
                    <Icon className={`h-5 w-5 ${color}`} />
                  </div>
                  <div>
                    <h3 className="font-bold text-white">{title}</h3>
                    <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p>
                  </div>
                </div>
                <Switch
                  checked={form[enabledKey]}
                  disabled={!data?.can_manage_channels || saving}
                  onCheckedChange={(checked) =>
                    setForm((old) => ({ ...old, [enabledKey]: checked }))
                  }
                  aria-label={`${title} aktivieren`}
                />
              </div>

              <div className="mt-5 rounded-xl border border-slate-800 bg-[#0e0e12] px-3.5 py-3">
                <div className="flex items-center gap-2 text-sm text-slate-300">
                  <Volume2 className="h-4 w-4 text-slate-600" />
                  <span className="truncate">{preview(count)}</span>
                </div>
              </div>

              <p className="mt-3 min-h-5 text-xs text-slate-600">
                {channel?.name
                  ? `Aktiv: ${channel.name}`
                  : form[enabledKey]
                    ? "Wird beim Speichern erstellt."
                    : "Kein Kanal aktiv."}
              </p>
            </div>
          );
        })}
      </div>

      <div className={`${CARD} flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between`}>
        <div>
          <h3 className="font-bold text-white">Automatische Aktualisierung</h3>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">
            Die Kanäle werden nach Beitritten und Austritten automatisch aktualisiert.
            Sie sind gesperrt, damit niemand ihnen beitreten kann. Beim Ausschalten wird
            nur der vom Bot angelegte Kanal entfernt.
          </p>
        </div>
        <button
          type="button"
          onClick={save}
          disabled={!changed || saving || !data?.can_manage_channels}
          className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-bold text-white transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Speichern
        </button>
      </div>
    </div>
  );
}
