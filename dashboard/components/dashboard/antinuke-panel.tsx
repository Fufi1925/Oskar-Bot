"use client";

import React, { useCallback, useState } from "react";
import {
  Activity,
  Bell,
  Bot,
  Check,
  Hash,
  Layers3,
  Pencil,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/i18n/LanguageContext";
import { translateWebsiteText } from "@/lib/i18n/dom-translations";
import { UserPicker } from "@/components/dashboard/user-picker";
import { InlineToggle } from "@/components/dashboard/form-elements";
import { Loading, usePanel } from "@/components/dashboard/save-bar";
import {
  SecurityCard as Card,
  SecurityMetrics,
  SecurityTabs,
  SecurityWarnings as Warnings,
} from "@/components/dashboard/security-workspace";

function actionIcon(key: string) {
  if (/channel|^ch/.test(key)) return Hash;
  if (/role|^rl/.test(key)) return Layers3;
  if (/bot/.test(key)) return Bot;
  if (/ban|kick|member|memup|prune/.test(key)) return Users;
  return Shield;
}

function WhitelistEditor({
  actions,
  initial,
  title,
  onCancel,
  onSave,
  busy,
}: any) {
  const [picked, setPicked] = useState<Record<string, boolean>>(initial || {});
  const count = actions.filter((a: any) => picked[a.key]).length;
  const all = actions.length > 0 && count === actions.length;
  return (
    <div className="cloudtix-security-whitelist-editor">
      <header>
        <strong>{title}</strong>
        <button
          type="button"
          disabled={busy || !actions.length}
          onClick={() =>
            setPicked(
              all
                ? {}
                : Object.fromEntries(actions.map((a: any) => [a.key, true])),
            )
          }
          className="cloudtix-security-text-button"
        >
          {all ? "Alle abwählen" : "Alle auswählen"}
        </button>
      </header>
      <div className="cloudtix-security-permissions">
        {actions.map((action: any) => (
          <button
            type="button"
            className="cloudtix-security-permission"
            key={action.key}
            disabled={busy}
            aria-pressed={!!picked[action.key]}
            onClick={() =>
              setPicked((p) => ({ ...p, [action.key]: !p[action.key] }))
            }
          >
            <span>{picked[action.key] && <Check size={12} />}</span>
            <span>
              <strong>{action.label}</strong>
              <small>{action.description}</small>
            </span>
          </button>
        ))}
      </div>
      <p
        className={all ? "cloudtix-settings-warning" : "cloudtix-security-note"}
      >
        {!count
          ? "Ohne Auswahl gilt der Schutz für dieses Mitglied vollständig weiter."
          : all
            ? "Alle Aktionen erlaubt: Gegen dieses Mitglied greift kein Anti-Nuke-Schutz. Es kann auch Kanäle und Rollen löschen."
            : `${count} von ${actions.length} Aktionen erlaubt. Alle übrigen Schutzbereiche bleiben aktiv.`}
      </p>
      <div className="cloudtix-security-button-row">
        <button
          type="button"
          disabled={busy}
          onClick={onCancel}
          className="cloudtix-workspace-action is-secondary"
        >
          Abbrechen
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onSave(picked)}
          className="cloudtix-workspace-action"
        >
          Ausnahme speichern
        </button>
      </div>
    </div>
  );
}

export function AntiNukePanel({
  guildId,
  reports,
}: {
  guildId: string;
  reports?: React.ReactNode;
}) {
  const { language } = useLanguage();
  const load = useCallback(() => api.getAntiNuke(guildId), [guildId]);
  const p = usePanel(load);
  const [adding, setAdding] = useState(false);
  const [newUser, setNewUser] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [view, setView] = useState("rules");
  const [query, setQuery] = useState("");

  if (p.loading) return <Loading />;

  if (!p.data)
    return (
      <Card icon={ShieldAlert} title="Anti-Nuke konnte nicht geladen werden">
        <button
          type="button"
          onClick={p.reload}
          className="text-sm text-blue-300"
        >
          Erneut laden
        </button>
      </Card>
    );
  const status = !!p.data?.status;
  const actions: any[] = p.data?.actions || [];
  const whitelist: any[] = p.data?.whitelist || [];
  const trustedBots: any[] = p.data?.trusted_bots || [];
  const activeActions = actions.filter(
    (action) => status && action.loaded && action.enabled !== false,
  );
  const visibleActions = actions.filter((action) =>
    `${action.label} ${action.description} ${translateWebsiteText(action.label, language)} ${translateWebsiteText(action.description, language)}`
      .toLocaleLowerCase()
      .includes(query.trim().toLocaleLowerCase()),
  );

  const unloaded = actions.filter((a) => !a.loaded).length;
  const fullyExempt = (entry: any) =>
    actions.length > 0 && actions.every((a) => !!entry.actions?.[a.key]);
  const toggleMaster = (v: boolean) =>
    p.act(
      () => api.updateAntiNuke(guildId, { status: v }),
      v
        ? undefined
        : "Anti-Nuke wirklich ausschalten? Ab dann kann jeder mit den passenden Rechten den Server leerräumen.",
    );

  return (
    <section className="cloudtix-settings-page cloudtix-security-page">
      <header className="cloudtix-settings-heading">
        <div>
          <p className="cloudtix-workspace-eyebrow">SICHERHEIT / ANTI-NUKE</p>
          <h1>Anti-Nuke</h1>
          <p>
            Überwache kritische Serveraktionen und lege gezielt fest, wem du
            Ausnahmen erlaubst.
          </p>
        </div>
        <div className="cloudtix-security-heading-actions">
          <div className="cloudtix-security-master">
            <span>Anti-Nuke aktivieren</span>
            <InlineToggle
              label=""
              ariaLabel="Anti-Nuke aktivieren"
              checked={status}
              disabled={p.busy}
              onCheckedChange={toggleMaster}
            />
          </div>
          <button
            type="button"
            onClick={p.reload}
            disabled={p.busy || adding || !!editing}
            className="cloudtix-settings-icon-button"
            aria-label="Anti-Nuke aktualisieren"
          >
            <RefreshCw size={17} />
          </button>
        </div>
      </header>
      <SecurityMetrics
        items={[
          {
            label: "Aktive Schutzbereiche",
            value: `${activeActions.length} / ${actions.length}`,
            icon: ShieldCheck,
            note: status
              ? "Geladen und eingeschaltet"
              : "Anti-Nuke ist ausgeschaltet",
          },
          {
            label: "Mitglied-Ausnahmen",
            value: whitelist.length,
            icon: Users,
            note: "Berechtigungen pro Aktion",
          },
          {
            label: "Nicht geladene Bereiche",
            value: unloaded,
            icon: Activity,
            note: unloaded
              ? "Diese Bereiche schützen aktuell nicht"
              : "Alle Schutzmodule sind geladen",
          },
        ]}
      />
      <Warnings items={p.data?.warnings} />
      <SecurityTabs
        value={view}
        onChange={setView}
        label="Anti-Nuke-Bereiche"
        items={[
          ["rules", "Schutzbereiche", Shield],
          ["exceptions", "Ausnahmen", Users],
          ["system", "System & Rechte", Activity],
          ["reports", "Angriffsmeldungen", Bell],
        ]}
      />
      <div hidden={view !== "rules"} className="space-y-5">
        <div className="cloudtix-security-subheading">
          <div>
            <h2>Was soll CloudTIX schützen?</h2>
            <p>
              Jeder Schalter wird sofort gespeichert. Beim Ausschalten fragt
              CloudTIX zur Sicherheit nach.
            </p>
          </div>
        </div>
        <div className="cloudtix-settings-running">
          <ShieldAlert size={20} />
          <p>
            {status
              ? "Der Bot bannt erkannte Angreifer und macht Aktionen rückgängig, soweit Discord es erlaubt. Rechte und Rollenposition sind dafür erforderlich."
              : "Der Hauptschalter ist aus. Kein Schutzbereich überwacht gerade deinen Server."}
          </p>
        </div>
        <div className="cloudtix-settings-search">
          <Search size={16} />
          <input
            className="cloudtix-security-input"
            aria-label="Schutzbereich suchen"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Schutzbereiche durchsuchen …"
          />
        </div>
        <div className="cloudtix-security-rules">
          {visibleActions.map((action) => {
            const enabled = action.enabled !== false;
            const available = status && action.loaded;
            const active = enabled && available;
            const Icon = actionIcon(action.key);
            return (
              <article
                key={action.key}
                className={`cloudtix-security-rule ${active ? "is-enabled" : ""} ${!action.loaded ? "is-unavailable" : ""}`}
              >
                <header className="cloudtix-security-rule-heading">
                  <span className="cloudtix-security-rule-icon">
                    <Icon size={18} />
                  </span>
                  <div>
                    <h3>{action.label}</h3>
                    <p>{action.description}</p>
                  </div>
                  <InlineToggle
                    label=""
                    ariaLabel={action.label}
                    checked={active}
                    disabled={p.busy || !available}
                    onCheckedChange={(v: boolean) =>
                      p.act(
                        () => api.setAntiNukeModule(guildId, action.key, v),
                        v
                          ? undefined
                          : `„${action.label}“ wirklich abschalten? Dieser Bereich wird dann nicht mehr überwacht.`,
                      )
                    }
                  />
                </header>
                <div className="cloudtix-security-rule-status">
                  <span className="cloudtix-settings-badge">
                    <i data-active={active} />
                    {!action.loaded
                      ? "Modul fehlt"
                      : !status
                        ? "Hauptschalter aus"
                        : active
                          ? "Überwachung aktiv"
                          : "Ausgeschaltet"}
                  </span>
                  <span>{action.modules?.length ?? 1} Wächter</span>
                </div>
              </article>
            );
          })}
        </div>
        {!visibleActions.length && (
          <div className="cloudtix-settings-empty">
            <Search size={26} />
            <h3>Keine passenden Schutzbereiche</h3>
            <p>Ändere den Suchbegriff.</p>
          </div>
        )}
      </div>
      <div hidden={view !== "exceptions"} className="space-y-5">
        <div className="cloudtix-security-subheading">
          <div>
            <h2>Vertrauen gezielt vergeben</h2>
            <p>
              Ein Mitglied wird nur für die ausgewählten Aktionen ausgenommen.
              Für alle übrigen gilt der Schutz weiter.
            </p>
          </div>
          {!adding && (
            <button
              type="button"
              disabled={p.busy}
              onClick={() => {
                setAdding(true);
                setEditing(null);
              }}
              className="cloudtix-workspace-action"
            >
              <UserPlus size={16} />
              Ausnahme hinzufügen
            </button>
          )}
        </div>
        {whitelist.some(fullyExempt) && (
          <Warnings
            items={[
              "Mindestens ein Mitglied ist von allen Schutzbereichen ausgenommen. Gegen dieses Mitglied greift Anti-Nuke nicht.",
            ]}
          />
        )}
        {adding && (
          <Card
            icon={UserPlus}
            title="Neue Mitglied-Ausnahme"
            subtitle="Wähle ein Mitglied und erlaube nur die benötigten Aktionen."
          >
            <UserPicker
              guildId={guildId}
              value={newUser}
              onChange={setNewUser}
              label="Mitglied"
              placeholder="Name suchen oder ID einfügen"
            />
            <WhitelistEditor
              actions={actions}
              initial={{}}
              title="Erlaubte Aktionen"
              busy={p.busy}
              onCancel={() => {
                setAdding(false);
                setNewUser("");
              }}
              onSave={async (picked: Record<string, boolean>) => {
                if (!newUser) return toast.error("Erst ein Mitglied wählen.");
                const saved = await p.act(() =>
                  api.setAntiNukeWhitelist(guildId, newUser, picked),
                );
                if (saved) {
                  setAdding(false);
                  setNewUser("");
                }
              }}
            />
          </Card>
        )}
        {!whitelist.length ? (
          <div className="cloudtix-settings-empty">
            <ShieldCheck size={30} />
            <h3>Keine Mitglied-Ausnahmen</h3>
            <p>Es sind keine persönlichen Sonderrechte vergeben.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {whitelist.map((entry) => {
              const allowed = actions.filter((a) => !!entry.actions?.[a.key]);
              const everything = fullyExempt(entry);
              const open = editing === entry.id;
              return (
                <article
                  key={entry.id}
                  className={`cloudtix-security-member ${everything ? "is-unrestricted" : ""}`}
                >
                  <div className="cloudtix-security-member-header">
                    {entry.avatar ? (
                      <img
                        src={entry.avatar}
                        alt=""
                        className="cloudtix-security-member-avatar"
                      />
                    ) : (
                      <span className="cloudtix-security-member-avatar">
                        <Users size={17} />
                      </span>
                    )}
                    <div>
                      <h3>
                        {entry.name || "Nicht mehr auf dem Server"}{" "}
                        {entry.bot && (
                          <span className="cloudtix-settings-badge">Bot</span>
                        )}
                      </h3>
                      <p>
                        {!allowed.length
                          ? "Keine Aktionen erlaubt · vollständiger Schutz"
                          : everything
                            ? "Alle Aktionen erlaubt · kein Schutz gegen dieses Mitglied"
                            : allowed.map((a) => a.label).join(" · ")}
                      </p>
                    </div>
                    <button
                      type="button"
                      disabled={p.busy}
                      className="cloudtix-settings-icon-button"
                      aria-label={`Ausnahme für ${entry.name || entry.id} bearbeiten`}
                      onClick={() => {
                        setEditing(open ? null : entry.id);
                        setAdding(false);
                      }}
                    >
                      <Pencil size={15} />
                    </button>
                    <button
                      type="button"
                      disabled={p.busy}
                      className="cloudtix-settings-icon-button is-danger"
                      aria-label={`Ausnahme für ${entry.name || entry.id} entfernen`}
                      onClick={() =>
                        p.act(
                          () => api.removeAntiNukeWhitelist(guildId, entry.id),
                          `${entry.name || entry.id} von der Ausnahmeliste entfernen?`,
                        )
                      }
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                  {open && (
                    <WhitelistEditor
                      actions={actions}
                      initial={entry.actions}
                      title={`Erlaubte Aktionen für ${entry.name || entry.id}`}
                      busy={p.busy}
                      onCancel={() => setEditing(null)}
                      onSave={async (picked: Record<string, boolean>) => {
                        const saved = await p.act(() =>
                          api.setAntiNukeWhitelist(guildId, entry.id, picked),
                        );
                        if (saved) setEditing(null);
                      }}
                    />
                  )}
                </article>
              );
            })}
          </div>
        )}
      </div>
      <div hidden={view !== "system"} className="cloudtix-settings-grid">
        <Card
          icon={Shield}
          title="Voraussetzungen für den Schutz"
          subtitle="Prüfe diese Einstellungen direkt auf deinem Discord-Server."
        >
          <div className="cloudtix-security-system-list">
            <div>
              <section>
                <strong>Bot-Rolle nach oben setzen</strong>
                <p>
                  CloudTIX kann nur Mitglieder bannen, deren höchste Rolle unter
                  der Bot-Rolle steht.
                </p>
              </section>
            </div>
            <div>
              <section>
                <strong>Benötigte Rechte vergeben</strong>
                <p>
                  „Mitglieder bannen“ und „Audit-Log einsehen“ sind nötig, um
                  Angreifer zu erkennen und zu bannen. Für Wiederherstellungen
                  braucht der Bot zusätzlich die entsprechenden
                  Verwaltungsrechte.
                </p>
              </section>
            </div>
            <div>
              <section>
                <strong>Discord-Grenzen beachten</strong>
                <p>
                  Gegen den Serverinhaber kann kein Bot vorgehen. Aktivierte
                  Module ersetzen keine passenden Discord-Rechte.
                </p>
              </section>
            </div>
          </div>
        </Card>
        <Card
          icon={Bot}
          title="Global vertraute Bots"
          subtitle="Diese Ausnahmen gelten auf allen Servern und werden vom Betreiber verwaltet."
        >
          {trustedBots.length ? (
            <div className="space-y-3">
              {trustedBots.map((b) => (
                <div key={b.id} className="cloudtix-security-member-header">
                  {b.avatar ? (
                    <img
                      alt=""
                      src={b.avatar}
                      className="cloudtix-security-member-avatar"
                    />
                  ) : (
                    <span className="cloudtix-security-member-avatar">
                      <Bot size={17} />
                    </span>
                  )}
                  <div>
                    <h3 className="text-sm">{b.name || "Unbekannter Bot"}</h3>
                    <p className="cloudtix-security-note">{b.id}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="cloudtix-security-note">
              Keine globalen Bot-Ausnahmen vorhanden.
            </p>
          )}
          <span className="cloudtix-settings-badge">Nur Ansicht</span>
        </Card>
      </div>
      <div hidden={view !== "reports"}>{reports}</div>
    </section>
  );
}
