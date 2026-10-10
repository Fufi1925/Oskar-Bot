"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  BarChart3,
  Bot,
  Crown,
  Globe2,
  Hash,
  Layers3,
  Loader2,
  Lock,
  Save,
  Server,
  Terminal,
  Users,
  UserRound,
  Volume2,
  RefreshCw,
} from "lucide-react";
import { toast } from "sonner";

import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import {
  SecurityCard,
  SecurityMetrics,
  SecurityWarnings,
} from "@/components/dashboard/security-workspace";
import {
  Loading,
  StickySaveBar,
  useSaveGuard,
} from "@/components/dashboard/save-bar";

type Kind =
  | "humans"
  | "bots"
  | "boosts"
  | "online"
  | "roles"
  | "channels"
  | "global_servers"
  | "global_users"
  | "global_commands";
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
    description:
      "Eindeutige Mitglieder aller verbundenen Server. Gemeinsame Mitglieder zählen einmal; fremde DM-Nutzer zählen nicht mit.",
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
  const [revision, setRevision] = useState(0);
  const premium = Boolean(data?.premium);
  const availableItems = ITEMS.filter(
    (item) =>
      (!item.premium || premium) &&
      (!item.global || data?.global_stats_available),
  );
  const changedItems = data
    ? availableItems.filter(
        ({ kind }) =>
          Boolean(data[`${kind}_enabled`]) !== form[`${kind}_enabled`],
      )
    : [];
  const dirtyCount = changedItems.length;
  const guard = useSaveGuard(dirtyCount, "server-stats-save-bar");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setData(null);
    setForm(EMPTY_FORM);
    api
      .getServerStats(guildId)
      .then((answer) => {
        if (cancelled) return;
        setData(answer);
        setForm(formFrom(answer));
      })
      .catch((error) => {
        if (!cancelled)
          toast.error(
            error?.message || "Server-Stats konnten nicht geladen werden.",
          );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [guildId, revision]);

  const save = async () => {
    if (!data?.can_manage_channels || !dirtyCount || saving) return;
    setSaving(true);
    try {
      // Only send switches available to this guild. The API also enforces permissions.
      const payload: Record<string, boolean> = {};
      for (const { kind } of availableItems)
        payload[`${kind}_enabled`] = form[`${kind}_enabled`];
      const answer = await api.updateServerStats(guildId, payload);
      setData(answer);
      setForm(formFrom(answer));
      toast.success("Server-Stats wurden aktualisiert.");
    } catch (error: any) {
      toast.error(
        error?.message || "Server-Stats konnten nicht gespeichert werden.",
      );
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <Loading />;
  if (!data)
    return (
      <SecurityCard
        icon={BarChart3}
        title="Server-Stats konnten nicht geladen werden"
      >
        <button
          type="button"
          className="cloudtix-workspace-action is-secondary"
          onClick={() => setRevision((r) => r + 1)}
        >
          <RefreshCw size={15} />
          Erneut versuchen
        </button>
      </SecurityCard>
    );

  const channelFor = (kind: Kind) =>
    data.channels?.[kind]?.name && !data.channels[kind].missing
      ? data.channels[kind]
      : null;
  const selected = availableItems.filter(({ kind }) => form[`${kind}_enabled`]);
  const managed = availableItems.filter(({ kind }) => !!channelFor(kind));
  const created = changedItems.filter(
    ({ kind }) => form[`${kind}_enabled`] && !channelFor(kind),
  );
  const removed = changedItems.filter(
    ({ kind }) => !form[`${kind}_enabled`] && channelFor(kind),
  );
  const renderItem = ({
    kind,
    title,
    description,
    icon: Icon,
    premium: required,
  }: (typeof ITEMS)[number]) => {
    const key = `${kind}_enabled` as keyof Form;
    const channel = channelFor(kind);
    const locked = !!required && !premium;
    const enabled = !locked && form[key];
    return (
      <article
        key={kind}
        className={`cloudtix-stats-item ${enabled ? "is-selected" : ""}`}
      >
        <header>
          <span className="cloudtix-security-rule-icon">
            <Icon size={18} />
          </span>
          <div>
            <h3>{title}</h3>
            <p>{description}</p>
          </div>
          {locked ? (
            <Lock size={16} className="text-neutral-500 mt-1" />
          ) : (
            <Switch
              aria-label={`${title} aktivieren`}
              checked={enabled}
              disabled={!data.can_manage_channels || saving}
              onCheckedChange={(checked) =>
                setForm((old) => ({ ...old, [key]: checked }))
              }
            />
          )}
        </header>
        <footer>
          <span>
            {locked
              ? "Mit Premium verfügbar"
              : channel
                ? enabled
                  ? `Aktiv: ${channel.name}`
                  : "Wird beim Speichern entfernt"
                : enabled
                  ? "Wird beim Speichern erstellt"
                  : "Kein Kanal aktiviert"}
          </span>
          <strong>
            {Number(data.counts?.[kind] || 0).toLocaleString("de-DE")}
          </strong>
        </footer>
      </article>
    );
  };

  return (
    <section className="cloudtix-settings-page cloudtix-security-page">
      <header className="cloudtix-settings-heading">
        <div>
          <p className="cloudtix-workspace-eyebrow">SERVER / STATISTIKEN</p>
          <h1>Server Stats</h1>
          <p>
            Zeige aktuelle Serverzahlen als Sprachkanäle an. CloudTIX hält sie
            automatisch auf dem neuesten Stand.
          </p>
        </div>
        <button
          type="button"
          className="cloudtix-workspace-action"
          onClick={save}
          disabled={!dirtyCount || saving || !data.can_manage_channels}
        >
          {saving ? (
            <Loader2 size={15} className="animate-spin" />
          ) : (
            <Save size={15} />
          )}
          Speichern
        </button>
      </header>
      <SecurityMetrics
        items={[
          {
            label: "Mitglieder ohne Bots",
            value: Number(data.counts?.humans || 0).toLocaleString("de-DE"),
            icon: Users,
            note: "Menschen auf diesem Server",
          },
          {
            label: "Verwaltete Statistikkanäle",
            value: managed.length,
            icon: Volume2,
            note: "Bereits vom Bot angelegte Kanäle",
          },
          {
            label: "Ausgewählte Zähler",
            value: selected.length,
            icon: BarChart3,
            note: dirtyCount
              ? `${dirtyCount} Änderungen im Entwurf`
              : "Gespeicherte Auswahl",
          },
        ]}
      />
      <SecurityWarnings
        items={
          data.warning
            ? [data.warning]
            : !data.can_manage_channels
              ? [
                  "CloudTIX benötigt „Kanäle verwalten“, um Statistikkanäle anzulegen, umzubenennen oder zu entfernen.",
                ]
              : []
        }
      />
      <div className="cloudtix-stats-layout">
        <div className="cloudtix-stats-groups">
          <section>
            <div className="cloudtix-security-subheading">
              <div>
                <h2>Die Grundlagen</h2>
                <p>Mitglieder, Bots und Boosts · für jeden Server verfügbar.</p>
              </div>
              <span className="cloudtix-settings-badge">Standard</span>
            </div>
            <div className="cloudtix-stats-items">
              {ITEMS.filter((item) => !item.premium && !item.global).map(
                renderItem,
              )}
            </div>
          </section>
          <section>
            <div className="cloudtix-security-subheading">
              <div>
                <h2>Noch mehr Einblicke</h2>
                <p>Online-Mitglieder, Rollen und Kanäle im Blick behalten.</p>
              </div>
              <span className="cloudtix-settings-badge">
                <Crown size={11} />
                Premium
              </span>
            </div>
            <div className="cloudtix-stats-items">
              {ITEMS.filter((item) => item.premium).map(renderItem)}
            </div>
            {!premium && (
              <div className="cloudtix-settings-premium-notice mt-4">
                <Crown size={23} />
                <div>
                  <h2>Zusätzliche Zähler freischalten</h2>
                  <p>
                    Aktiviere Premium für diesen Server, um diese Statistiken zu
                    verwenden.
                  </p>
                </div>
                <Link
                  href={`/dashboard/guild/${guildId}/premium`}
                  className="cloudtix-workspace-action is-secondary"
                >
                  Premium ansehen
                </Link>
              </div>
            )}
          </section>
          {data.global_stats_available && (
            <section>
              <div className="cloudtix-security-subheading">
                <div>
                  <h2>Das CloudTIX-Netzwerk</h2>
                  <p>Globale Zahlen · exklusiv für den Main-Support-Server.</p>
                </div>
                <Globe2 size={19} className="text-neutral-400" />
              </div>
              <div className="cloudtix-stats-items">
                {ITEMS.filter((item) => item.global).map(renderItem)}
              </div>
            </section>
          )}
        </div>
        <aside className="cloudtix-stats-preview space-y-5">
          <SecurityCard
            icon={Volume2}
            title="So sieht es auf Discord aus"
            subtitle="Vorschau deiner Auswahl. Änderungen erscheinen nach dem Speichern."
          >
            <div className="cloudtix-stats-channel-list">
              <p>SERVER-STATISTIKEN</p>
              {selected.length ? (
                selected.map((item) => (
                  <div
                    key={item.kind}
                    className={`cloudtix-stats-channel ${!channelFor(item.kind) ? "is-pending" : ""}`}
                  >
                    <Volume2 size={16} />
                    <span>
                      {channelFor(item.kind)?.name ||
                        item.preview(Number(data.counts?.[item.kind] || 0))}
                    </span>
                    <Lock size={11} />
                  </div>
                ))
              ) : (
                <p className="cloudtix-security-note py-4">
                  Wähle einen Zähler, um die Kanalvorschau zu sehen.
                </p>
              )}
            </div>
            {dirtyCount > 0 && (
              <div className="cloudtix-settings-details">
                <div>
                  <dt>Neue Kanäle</dt>
                  <dd>{created.length}</dd>
                </div>
                <div>
                  <dt>Kanäle entfernen</dt>
                  <dd>{removed.length}</dd>
                </div>
              </div>
            )}
            <p className="cloudtix-security-note">
              Gestrichelte Kanäle werden neu angelegt. Bestehende Kanäle
              behalten ihren aktuellen Namen bis zur nächsten Aktualisierung.
            </p>
          </SecurityCard>
          <SecurityCard icon={Activity} title="Automatisch aktuell">
            <div className="cloudtix-security-system-list">
              <div>
                <section>
                  <strong>Zahlen ohne Handarbeit</strong>
                  <p>
                    CloudTIX aktualisiert die Kanalnamen automatisch mit den
                    aktuellen Werten.
                  </p>
                </section>
              </div>
              <div>
                <section>
                  <strong>Nur zum Anzeigen</strong>
                  <p>
                    Die Sprachkanäle sind gesperrt, damit niemand ihnen
                    beitritt.
                  </p>
                </section>
              </div>
              <div>
                <section>
                  <strong>Kontrolliert entfernen</strong>
                  <p>
                    Beim Ausschalten wird ausschließlich der vom Bot verwaltete
                    Statistikkanal entfernt.
                  </p>
                </section>
              </div>
            </div>
          </SecurityCard>
        </aside>
      </div>
      <StickySaveBar
        id="server-stats-save-bar"
        count={dirtyCount}
        busy={saving}
        shake={guard.shake}
        blocked={
          !data.can_manage_channels
            ? "CloudTIX benötigt das Recht „Kanäle verwalten“."
            : null
        }
        onDiscard={() => setForm(formFrom(data))}
        onSave={save}
      />
    </section>
  );
}
