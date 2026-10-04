"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  Bot, Crown, Globe2, Hash, Layers3, Loader2, Lock, Save, Server, Terminal,
  Users, UserRound, Volume2,
} from "lucide-react";
import { toast } from "sonner";

import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";

const CARD = "rounded-3xl border border-slate-800 bg-[#131318]";

type Kind =
  | "humans" | "bots" | "boosts" | "online" | "roles" | "channels"
  | "global_servers" | "global_users" | "global_commands";
type Form = Record<`${Kind}_enabled`, boolean>;

const ITEMS: Array<{
  kind: Kind;
  title: string;
  description: string;
  preview: (count: number) => string;
  icon: typeof Users;
  color: string;
  premium?: boolean;
  global?: boolean;
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
    kind: "boosts",
    title: "Server-Boosts",
    description: "Zeigt die aktuelle Anzahl der Server-Boosts.",
    preview: (count) => `🚀 Boosts: ${count}`,
    icon: Crown,
    color: "text-pink-400",
  },
  {
    kind: "online",
    title: "Online-Nutzer",
    description: "Zählt alle Menschen, die gerade nicht offline sind.",
    preview: (count) => `🟢 Online: ${count}`,
    icon: Users,
    color: "text-emerald-400",
    premium: true,
  },
  {
    kind: "roles",
    title: "Rollen",
    description: "Zählt alle Serverrollen außer @everyone.",
    preview: (count) => `🎭 Rollen: ${count}`,
    icon: Layers3,
    color: "text-amber-400",
    premium: true,
  },
  {
    kind: "channels",
    title: "Kanäle",
    description: "Zählt alle Text-, Sprach-, Forum- und Kategoriekanäle.",
    preview: (count) => `📚 Kanäle: ${count}`,
    icon: Hash,
    color: "text-cyan-400",
    premium: true,
  },
  {
    kind: "global_servers",
    title: "Alle Server",
    description: "Zeigt live, auf wie vielen Servern der Bot aktiv ist.",
    preview: (count) => `🌐 Alle Server: ${count}`,
    icon: Server,
    color: "text-blue-400",
    global: true,
  },
  {
    kind: "global_users",
    title: "Alle Nutzer",
    description: "Zeigt die live erreichbaren, eindeutigen Nutzer des Bots.",
    preview: (count) => `👥 Alle Nutzer: ${count}`,
    icon: Globe2,
    color: "text-indigo-400",
    global: true,
  },
  {
    kind: "global_commands",
    title: "Ausgeführte Befehle",
    description: "Zeigt alle seit Beginn erfassten Prefix- und Slash-Befehle.",
    preview: (count) => `⌨️ Befehle: ${count}`,
    icon: Terminal,
    color: "text-violet-400",
    global: true,
  },
];

const EMPTY_FORM: Form = {
  humans_enabled: false,
  bots_enabled: false,
  boosts_enabled: false,
  online_enabled: false,
  roles_enabled: false,
  channels_enabled: false,
  global_servers_enabled: false,
  global_users_enabled: false,
  global_commands_enabled: false,
};

function formFrom(answer: any): Form {
  return {
    humans_enabled: Boolean(answer.humans_enabled),
    bots_enabled: Boolean(answer.bots_enabled),
    boosts_enabled: Boolean(answer.boosts_enabled),
    online_enabled: Boolean(answer.online_enabled),
    roles_enabled: Boolean(answer.roles_enabled),
    channels_enabled: Boolean(answer.channels_enabled),
    global_servers_enabled: Boolean(answer.global_servers_enabled),
    global_users_enabled: Boolean(answer.global_users_enabled),
    global_commands_enabled: Boolean(answer.global_commands_enabled),
  };
}

export function ServerStatsPanel({ guildId }: { guildId: string }) {
  const [data, setData] = useState<any>(null);
  const [form, setForm] = useState<Form>(EMPTY_FORM);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getServerStats(guildId)
      .then((answer) => {
        if (cancelled) return;
        setData(answer);
        setForm(formFrom(answer));
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
      // Premium-Schalter werden nicht bloß im Browser gesperrt. Ohne
      // Premium schicken wir sie gar nicht erst; die API prüft zusätzlich.
      const payload: Record<string, boolean> = data?.premium
        ? { ...form }
        : {
            humans_enabled: form.humans_enabled,
            bots_enabled: form.bots_enabled,
            boosts_enabled: form.boosts_enabled,
          };
      if (data?.global_stats_available) {
        payload.global_servers_enabled = form.global_servers_enabled;
        payload.global_users_enabled = form.global_users_enabled;
        payload.global_commands_enabled = form.global_commands_enabled;
      }
      const answer = await api.updateServerStats(guildId, payload);
      setData(answer);
      setForm(formFrom(answer));
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

  const premium = Boolean(data?.premium);
  const changed = data && ITEMS.some(({ kind, premium: required, global }) =>
    (!required || premium) &&
    (!global || data.global_stats_available) &&
    Boolean(data[`${kind}_enabled`]) !== form[`${kind}_enabled`]
  );

  const renderItem = ({
    kind, title, description, preview, icon: Icon, color, premium: required,
  }: (typeof ITEMS)[number]) => {
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
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-white">{title}</h3>
                {required && (
                  <span className="rounded-full border border-amber-400/20 bg-amber-400/10 px-2 py-0.5 text-[9px] font-black uppercase tracking-wider text-amber-300">
                    Premium
                  </span>
                )}
              </div>
              <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p>
            </div>
          </div>
          <Switch
            checked={form[enabledKey]}
            disabled={!data?.can_manage_channels || saving || (Boolean(required) && !premium)}
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
  };

  return (
    <div className="space-y-5">
      {data?.warning && (
        <div className="rounded-2xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          {data.warning} Ohne dieses Recht kann der Bot keine Statistikkanäle anlegen oder umbenennen.
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        {ITEMS.filter((item) => !item.premium && !item.global).map(renderItem)}
      </div>

      <div className="space-y-3">
        <div className="flex items-center gap-2 px-1">
          <Crown className="h-4 w-4 text-amber-400" />
          <h3 className="text-sm font-bold text-white">Weitere Statistiken mit Premium</h3>
        </div>
        <div className="relative overflow-hidden rounded-3xl">
          <div
            className={`grid gap-4 lg:grid-cols-3 transition ${
              premium ? "" : "pointer-events-none select-none blur-[3px] opacity-45"
            }`}
            aria-hidden={!premium}
          >
            {ITEMS.filter((item) => item.premium).map(renderItem)}
          </div>

          {!premium && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#0a0a0c]/35 p-4">
              <div className="max-w-sm rounded-2xl border border-amber-400/25 bg-[#131318]/95 p-5 text-center shadow-2xl backdrop-blur-md">
                <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-amber-400/10">
                  <Lock className="h-5 w-5 text-amber-300" />
                </div>
                <h3 className="mt-3 font-bold text-white">Premium erforderlich</h3>
                <p className="mt-1 text-sm leading-5 text-slate-400">
                  Online-Nutzer, Rollen und Kanäle sind zusätzliche Premium-Statistiken.
                </p>
                <Link
                  href="/premium"
                  className="mt-4 inline-flex items-center gap-2 rounded-xl bg-amber-400 px-4 py-2 text-sm font-bold text-black transition hover:bg-amber-300"
                >
                  <Crown className="h-4 w-4" />
                  Premium ansehen
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>

      {data?.global_stats_available && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 px-1">
            <Globe2 className="h-4 w-4 text-indigo-400" />
            <div>
              <h3 className="text-sm font-bold text-white">Globale Bot-Statistiken</h3>
              <p className="text-xs text-slate-500">
                Exklusiv für den Main-Support-Server · live über alle Server
              </p>
            </div>
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            {ITEMS.filter((item) => item.global).map(renderItem)}
          </div>
        </div>
      )}

      <div className={`${CARD} flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between`}>
        <div>
          <h3 className="font-bold text-white">Automatische Aktualisierung</h3>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">
            Die Kanäle werden automatisch aktualisiert. Sie sind gesperrt, damit
            niemand ihnen beitreten kann. Beim Ausschalten wird nur der vom Bot
            angelegte Kanal entfernt.
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
