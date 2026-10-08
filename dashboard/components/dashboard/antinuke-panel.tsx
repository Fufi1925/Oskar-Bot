"use client";

import { ModerationTabs } from "@/components/dashboard/moderation-design";
import React, { useCallback, useState } from "react";
import {
  AlertTriangle, Bot, Check, ChevronDown, Pencil, Shield, ShieldAlert,
  ShieldCheck, Trash2, UserPlus, Search, RefreshCw,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/i18n/LanguageContext";
import { translateWebsiteText } from "@/lib/i18n/dom-translations";
import { cn } from "@/lib/utils";
import { UserPicker } from "@/components/dashboard/user-picker";
import { InlineToggle } from "@/components/dashboard/form-elements";
import { Loading, usePanel } from "@/components/dashboard/save-bar";

function Card({ icon: Icon, title, subtitle, children, tone }: any) {
  return (
    <div
      className={cn(
        "border rounded-2xl p-4 sm:p-6 space-y-5",
        tone === "danger"
          ? "bg-red-500/[0.04] border-red-500/25"
          : "bg-[#202124] border-white/[.07]"
      )}
    >
      <div className="flex gap-3 min-w-0">
        <div
          className={cn(
            "h-10 w-10 rounded-2xl grid place-items-center shrink-0",
            tone === "danger" ? "bg-red-500/15" : "bg-primary/15"
          )}
        >
          <Icon
            className={cn(
              "h-5 w-5",
              tone === "danger" ? "text-red-400" : "text-primary"
            )}
          />
        </div>
        <div className="min-w-0">
          <p className="font-semibold text-white">{title}</p>
          {subtitle && (
            <p className="text-xs text-slate-400 mt-1 leading-relaxed">
              {subtitle}
            </p>
          )}
        </div>
      </div>
      {children}
    </div>
  );
}

function Warnings({ items }: { items?: string[] }) {
  if (!items?.length) return null;
  return (
    <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/20 p-3.5 flex gap-2.5">
      <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
      <div className="text-xs text-amber-200/80 leading-relaxed">
        <span className="font-bold">Das solltest du wissen:</span>
        <br />
        {items.map((w, i) => (
          <span key={i}>
            • {w}
            <br />
          </span>
        ))}
      </div>
    </div>
  );
}

/** Add or edit one whitelist entry. Nothing is ticked to begin with. */
function WhitelistEditor({
  actions,
  initial,
  title,
  onCancel,
  onSave,
  busy,
}: any) {
  const [picked, setPicked] = useState<Record<string, boolean>>(initial || {});
  const count = Object.values(picked).filter(Boolean).length;
  const all = count === actions.length;

  return (
    <div className="rounded-2xl bg-[#18191c] border border-white/[.07] p-4 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">
          {title}
        </p>
        <button
          disabled={busy}
          onClick={() =>
            setPicked(
              all
                ? {}
                : Object.fromEntries(actions.map((a: any) => [a.key, true]))
            )
          }
          className="text-xs text-slate-500 hover:text-slate-300 underline shrink-0"
        >
          {all ? "Nichts" : "Alles"}
        </button>
      </div>

      <div className="grid sm:grid-cols-2 gap-2">
        {actions.map((action: any) => {
          const on = !!picked[action.key];
          return (
            <button
              key={action.key}
              disabled={busy}
              onClick={() => setPicked((p) => ({ ...p, [action.key]: !on }))}
              title={action.description}
              className={cn(
                "flex items-start gap-2.5 text-left rounded-xl border px-3 py-2.5 transition-all",
                on
                  ? "bg-red-500/10 border-red-500/40"
                  : "bg-[#18191c] border-white/[.07] hover:border-slate-700"
              )}
            >
              <span
                className={cn(
                  "h-4 w-4 rounded grid place-items-center shrink-0 mt-0.5 border",
                  on ? "bg-red-500/80 border-red-500" : "border-slate-700"
                )}
              >
                {on && <Check className="h-3 w-3 text-white" />}
              </span>
              <span className="min-w-0">
                <span
                  className={cn(
                    "block text-xs font-bold",
                    on ? "text-white" : "text-slate-400"
                  )}
                >
                  {action.label}
                </span>
                <span className="block text-xs text-slate-500 leading-relaxed">
                  {action.description}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      <p
        className={cn(
          "text-xs leading-relaxed",
          count === 0 ? "text-slate-500" : "text-amber-200/70"
        )}
      >
        {count === 0
          ? "Nichts angehakt: Für diese Person gilt der Schutz vollständig weiter."
          : all
          ? "Alles angehakt: Diese Person kann den Server ungehindert zerlegen. Nur für Konten, denen du das wirklich zutraust."
          : `${count} von ${actions.length} Aktionen erlaubt. Bei allen anderen greift der Schutz weiter.`}
      </p>

      <div className="flex gap-2">
        <button
          onClick={onCancel}
          disabled={busy}
          className="px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-semibold uppercase tracking-widest text-slate-400 hover:text-white disabled:opacity-40 transition-all"
        >
          Abbrechen
        </button>
        <button
          onClick={() => onSave(picked)}
          disabled={busy}
          className="flex-1 py-2.5 rounded-xl bg-primary text-xs font-semibold uppercase tracking-widest hover:brightness-110 disabled:opacity-40 transition-all"
        >
          Speichern
        </button>
      </div>
    </div>
  );
}

export function AntiNukePanel({ guildId, reports }: { guildId: string; reports?: React.ReactNode }) {
  const { language } = useLanguage();
  const load = useCallback(() => api.getAntiNuke(guildId), [guildId]);
  const p = usePanel(load);
  const [adding, setAdding] = useState(false);
  const [newUser, setNewUser] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [view, setView] = useState("rules");
  const [query, setQuery] = useState("");

  if (p.loading) return <Loading />;

  if (!p.data) return <Card icon={ShieldAlert} title="Anti-Nuke konnte nicht geladen werden"><button type="button" onClick={p.reload} className="text-sm text-blue-300">Erneut laden</button></Card>;
  const status = !!p.data?.status;
  const actions: any[] = p.data?.actions || [];
  const whitelist: any[] = p.data?.whitelist || [];
  const trustedBots: any[] = p.data?.trusted_bots || [];
  const activeActions = actions.filter(action => status && action.loaded && action.enabled !== false);
  const visibleActions = actions.filter(action => `${action.label} ${action.description} ${translateWebsiteText(action.label, language)} ${translateWebsiteText(action.description, language)}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));

  return (
    <section className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-3">
        {[{ label: "Aktive Schutzbereiche", value: activeActions.length }, { label: "Ausnahmen", value: whitelist.length }, { label: "Nicht geladene Bereiche", value: actions.filter(a => !a.loaded).length }].map(item => <div key={item.label} className="rounded-2xl border border-white/[.07] bg-[#202124] p-5"><p className="text-xs text-slate-400">{item.label}</p><p className="mt-2 text-2xl font-semibold text-white">{item.value}</p></div>)}
      </div>
      <Warnings items={p.data?.warnings} />
      <ModerationTabs value={view} onChange={setView} items={[["rules", "Schutzbereiche"], ["exceptions", "Ausnahmen"], ["system", "Systeminfos"], ["reports", "Angriffsmeldungen"]]} label="Anti-Nuke-Bereiche" />

      {/* Die vertrauten Bots aus `TRUSTED_BOTS`.
          Nur zum Anschauen -- die Liste gilt global und wird in
          Railway gesetzt, nicht hier. Sie steht trotzdem im Reiter,
          weil sonst niemand nachvollziehen kann, warum ein
          bestimmter Bot ungestraft Kanäle anlegt. Von außen sieht
          das aus wie ein kaputter Anti-Nuke. */}
      <div hidden={view !== "system"} className="space-y-5">
      {trustedBots.length > 0 && (
        <div className="rounded-2xl border border-white/[.07] bg-[#202124] p-4">
          <div className="flex items-start gap-3">
            <Bot className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
            <div className="min-w-0 flex-1">
              <p className="text-[14px] font-semibold text-white">
                {trustedBots.length}{" "}
                {trustedBots.length === 1 ? "Bot wird" : "Bots werden"} nie
                angegriffen
              </p>
              <p className="mt-1 text-[13px] leading-relaxed text-slate-500">
                Bekannte Bots, die Kanäle anlegen und Rollen vergeben — also
                aussehen wie ein Angriff. Die Liste gilt für alle Server und
                lässt sich nur vom Betreiber ändern.
              </p>
              {/* Mit Profilbild und Namen, nicht nur der ID.
                  Eine 19-stellige Zahl sagt niemandem, welcher Bot da
                  geschützt ist — und genau das ist die Frage, die man
                  sich hier stellt. Kennt der Bot das Konto nicht,
                  bleibt die ID stehen: ehrlicher als ein erfundener
                  Name. */}
              <div className="mt-3 flex flex-wrap gap-2">
                {trustedBots.map((b: any) => (
                  <span
                    key={b.id}
                    title={`${b.name || "Unbekannt"} · ${b.id}`}
                    className="flex items-center gap-2 rounded-lg border border-white/[.07] bg-[#18191c] py-1 pl-1 pr-2.5"
                  >
                    {b.avatar ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={b.avatar}
                        alt=""
                        width={20}
                        height={20}
                        className="h-5 w-5 rounded-full object-cover"
                      />
                    ) : (
                      <span className="grid h-5 w-5 place-items-center rounded-full bg-slate-800">
                        <Bot className="h-3 w-3 text-slate-500" />
                      </span>
                    )}
                    <span className="text-xs text-slate-300">
                      {b.name || b.id}
                    </span>
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      <Card
        icon={Shield}
        title="Damit der Schutz auch greift"
        subtitle="Drei Dinge, ohne die Anti-Nuke nur zuschaut."
      >
        <div className="space-y-3 text-xs text-slate-400 leading-relaxed">
          <p>
            <b className="text-slate-200">Rolle ganz oben:</b> Der Bot kann
            niemanden bannen, der über ihm steht. Die Bot-Rolle gehört an die
            Spitze der Rollenliste.
          </p>
          <p>
            <b className="text-slate-200">Rechte:</b> „Mitglieder bannen“ und
            „Audit-Log einsehen“. Ohne das zweite erfährt der Bot nicht
            einmal, wer etwas gelöscht hat.
          </p>
          <p>
            <b className="text-slate-200">Serverinhaber:</b> Gegen den
            Server-Eigentümer kann kein Bot etwas ausrichten — das lässt
            Discord grundsätzlich nicht zu.
          </p>
        </div>
      </Card>
      {trustedBots.length === 0 && <Card icon={Bot} title="Vertrauenswürdige Bots"><p className="text-sm text-slate-400">Keine globalen Bot-Ausnahmen vorhanden.</p></Card>}
      </div>
      <div hidden={view !== "rules"}>
      <Card
        icon={status ? ShieldCheck : ShieldAlert}
        title="Anti-Nuke"
        subtitle="Wenn jemand anfängt, Kanäle zu löschen oder Mitglieder zu bannen, bannt der Bot die Person und macht rückgängig, was geht."
      >
        <div
          className={cn(
            "rounded-2xl border p-4 flex items-center justify-between gap-4",
            status
              ? "bg-emerald-500/[0.06] border-emerald-500/25"
              : "bg-[#18191c] border-white/[.07]"
          )}
        >
          <div className="min-w-0">
            <p
              className={cn(
                "font-semibold",
                status ? "text-emerald-300" : "text-slate-400"
              )}
            >
              {status ? "Aktiv" : "Aus"}
            </p>
            <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
              {status
                ? `${activeActions.reduce((count, action) => count + (action.modules?.length ?? 1), 0)} Wächter laufen mit.`
                : "Es wird nichts überwacht."}
            </p>
          </div>
          <InlineToggle
            ariaLabel="Anti-Nuke"
            checked={status}
            onCheckedChange={(v: boolean) =>
              p.act(
                () => api.updateAntiNuke(guildId, { status: v }),
                v
                  ? undefined
                  : "Anti-Nuke wirklich ausschalten? Ab dann kann jeder mit den passenden Rechten den Server leerräumen."
              )
            }
            label=""
            disabled={p.busy}
          />
        </div>

        <div className="relative"><Search className="absolute left-3 top-3.5 h-4 w-4 text-slate-500" /><input value={query} onChange={e => setQuery(e.target.value)} aria-label="Schutzbereich suchen" placeholder="Schutzbereich suchen …" className="w-full rounded-xl border border-white/10 bg-[#18191c] py-3 pl-10 pr-4 text-sm text-white outline-none focus:border-blue-400/40" /></div>
        <button type="button" onClick={p.reload} disabled={p.busy} className="flex items-center gap-2 text-sm text-blue-300"><RefreshCw className="h-4 w-4" />Status aktualisieren</button>
        <div className="grid sm:grid-cols-2 gap-2">
            {/* Jeder Bereich ist jetzt ein eigener Schalter.
                Vorher war das eine reine Anzeige: wer wollte, dass der
                Bot Kanal-Löschungen ignoriert (weil ein anderer Bot
                dauernd welche anlegt), musste den ganzen Anti-Nuke
                ausschalten — und stand dann komplett ohne Schutz da.

                Die Schalter sind grau, solange der Hauptschalter aus
                ist: sie hätten dann keine Wirkung, und ein bedienbarer
                Schalter ohne Wirkung ist eine Lüge. */}
            {visibleActions.map((action) => {
              const an = action.enabled !== false;
              const nutzbar = status && action.loaded;
              return (
                <div
                  key={action.key}
                  className={cn(
                    "rounded-xl border px-3 py-2.5 flex items-start justify-between gap-3",
                    !action.loaded
                      ? "bg-red-500/[0.05] border-red-500/25"
                      : !status
                      ? "bg-[#18191c]/50 border-white/[.05]"
                      : an
                      ? "bg-[#18191c] border-white/[.07]"
                      : "bg-[#18191c]/50 border-white/[.05]"
                  )}
                >
                  <div className="min-w-0">
                    <p
                      className={cn(
                        "text-xs font-bold",
                        nutzbar && an ? "text-white" : "text-slate-500"
                      )}
                    >
                      {action.label}
                    </p>
                    <p className="text-xs text-slate-500 leading-relaxed mt-0.5">
                      {!action.loaded
                        ? "Dieses Modul ist nicht geladen — es schützt gerade nichts."
                        : !status
                        ? "Der Hauptschalter ist aus."
                        : an
                        ? action.description
                        : "Abgeschaltet — dieser Bereich wird nicht überwacht."}
                    </p>
                  </div>

                  <InlineToggle
                    ariaLabel={action.label}
                    checked={an && nutzbar}
                    onCheckedChange={(v: boolean) =>
                      p.act(
                        () => api.setAntiNukeModule(guildId, action.key, v),
                        v
                          ? undefined
                          : `„${action.label}“ wirklich abschalten? Dieser Bereich wird dann nicht mehr überwacht.`
                      )
                    }
                    label=""
                    disabled={p.busy || !nutzbar}
                  />
                </div>
              );
            })}
          </div>
        {visibleActions.length === 0 && <p className="py-6 text-center text-sm text-slate-400">Keine passenden Schutzbereiche.</p>}

        <p className="text-xs text-slate-500 leading-relaxed">
          Jeder Schutzbereich ist einzeln einstellbar. Eine Ausnahme erlaubt einer Person nur die ausgewählten Aktionen.
        </p>
      </Card>

      </div>
      <div hidden={view !== "exceptions"}>
      {/* ── Whitelist ────────────────────────────────────────── */}
      <Card
        icon={UserPlus}
        title="Ausnahmeliste"
        subtitle="Wer hier steht, wird für die angehakten Aktionen nicht gestoppt. Alles andere gilt weiter."
        tone={whitelist.some((e) => Object.values(e.actions).every(Boolean)) ? "danger" : undefined}
      >
        {!adding && (
          <button
            onClick={() => {
              setAdding(true);
              setEditing(null);
            }}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-semibold uppercase tracking-widest text-slate-300 hover:text-white transition-all"
          >
            <UserPlus className="h-3.5 w-3.5" />
            Jemanden ausnehmen
          </button>
        )}

        {adding && (
          <div className="space-y-3">
            <UserPicker
              guildId={guildId}
              value={newUser}
              onChange={setNewUser}
              label="Mitglied"
              placeholder="Suchen oder ID einfügen"
            />
            <WhitelistEditor
              actions={actions}
              initial={{}}
              title="Was darf diese Person?"
              busy={p.busy}
              onCancel={() => {
                setAdding(false);
                setNewUser("");
              }}
              onSave={async (picked: Record<string, boolean>) => {
                if (!newUser) return toast.error("Erst ein Mitglied wählen.");
                const saved = await p.act(() => api.setAntiNukeWhitelist(guildId, newUser, picked));
                if (!saved) return;
                setAdding(false);
                setNewUser("");
              }}
            />
          </div>
        )}

        {whitelist.length === 0 ? (
          <p className="text-sm text-slate-500 py-8 text-center border border-dashed border-white/[.07] rounded-2xl">
            Niemand ausgenommen. Der Schutz gilt für alle — auch für dich.
          </p>
        ) : (
          <div className="space-y-2">
            {whitelist.map((entry) => {
              const allowed = Object.entries(entry.actions).filter(
                ([, on]) => on
              );
              const everything = allowed.length === actions.length;
              const open = editing === entry.id;
              return (
                <div
                  key={entry.id}
                  className={cn(
                    "rounded-2xl border",
                    everything
                      ? "bg-red-500/[0.05] border-red-500/30"
                      : "bg-[#18191c] border-white/[.07]"
                  )}
                >
                  <div className="flex items-center gap-3 px-4 py-3">
                    {entry.avatar ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={entry.avatar}
                        alt=""
                        className="h-8 w-8 rounded-full shrink-0"
                      />
                    ) : (
                      <div className="h-8 w-8 rounded-full bg-slate-800 shrink-0" />
                    )}
                    <div className="min-w-0 flex-1">
                      <p
                        className={cn(
                          "text-sm font-bold truncate",
                          entry.missing ? "text-slate-500 italic" : "text-white"
                        )}
                      >
                        {entry.name || "Nicht mehr auf dem Server"}
                        {entry.bot && (
                          <span className="ml-2 px-1.5 py-0.5 rounded bg-primary/15 text-primary text-xs font-semibold uppercase align-middle">
                            Bot
                          </span>
                        )}
                      </p>
                      <p
                        className={cn(
                          "text-xs truncate",
                          everything ? "text-red-300" : "text-slate-500"
                        )}
                      >
                        {allowed.length === 0
                          ? "darf nichts — wirkt wie keine Ausnahme"
                          : everything
                          ? "darf alles — kein Schutz gegen diese Person"
                          : allowed
                              .map(
                                ([key]) =>
                                  actions.find((a) => a.key === key)?.label || key
                              )
                              .join(", ")}
                      </p>
                    </div>
                    <button
                      onClick={() => {
                        setEditing(open ? null : entry.id);
                        setAdding(false);
                      }}
                      className="p-2 rounded-lg text-slate-500 hover:text-white hover:bg-white/5 shrink-0 transition-colors"
                      title="Ändern"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() =>
                        p.act(
                          () => api.removeAntiNukeWhitelist(guildId, entry.id),
                          `${entry.name || entry.id} von der Ausnahmeliste entfernen?`
                        )
                      }
                      className="p-2 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10 shrink-0 transition-colors"
                      title="Entfernen"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>

                  {open && (
                    <div className="px-4 pb-4">
                      <WhitelistEditor
                        actions={actions}
                        initial={entry.actions}
                        title={`Was darf ${entry.name || entry.id}?`}
                        busy={p.busy}
                        onCancel={() => setEditing(null)}
                        onSave={async (picked: Record<string, boolean>) => {
                          const saved = await p.act(() => api.setAntiNukeWhitelist(guildId, entry.id, picked));
                          if (!saved) return;
                          setEditing(null);
                        }}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>


      </div>
      <div hidden={view !== "reports"}>{reports}</div>
    </section>
  );
}
