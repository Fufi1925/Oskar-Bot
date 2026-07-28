"use client";

/**
 * Anti-Nuke.
 *
 * What this replaces: four cards labelled "Anti Ban & Kick",
 * "Anti Server Edit", "Anti Role Modifier" and "Anti Channel Nukes",
 * each with a green &bdquo;Protected&ldquo; badge. Those four ids appear
 * nowhere in the bot -- the real thing is seventeen listeners covering
 * fourteen kinds of action, and none of them is individually
 * switchable. So the tab showed four labels that stood for nothing and
 * hid ten kinds of protection that do exist.
 *
 * The whitelist was worse. The table has one column per action and each
 * module reads only its own, but the dashboard's &bdquo;Add&ldquo;
 * button wrote every column as true -- a complete bypass of all
 * seventeen protections, from a button with no warning on it. Here you
 * pick the actions, and the default is none.
 */

import React, { useCallback, useState } from "react";
import {
  AlertTriangle, Check, ChevronDown, Pencil, Shield, ShieldAlert,
  ShieldCheck, Trash2, UserPlus,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { UserPicker } from "@/components/dashboard/user-picker";
import { InlineToggle } from "@/components/dashboard/form-elements";
import { Loading, usePanel } from "@/components/dashboard/save-bar";

function Card({ icon: Icon, title, subtitle, children, tone }: any) {
  return (
    <div
      className={cn(
        "border rounded-3xl p-6 space-y-5",
        tone === "danger"
          ? "bg-red-500/[0.04] border-red-500/25"
          : "bg-[#10233f] border-slate-800"
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
          <p className="font-black text-white">{title}</p>
          {subtitle && (
            <p className="text-[12px] text-slate-400 mt-1 leading-relaxed">
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
      <div className="text-[12px] text-amber-200/80 leading-relaxed">
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
    <div className="rounded-2xl bg-[#0d1b31] border border-slate-800 p-4 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-black uppercase tracking-widest text-slate-400">
          {title}
        </p>
        <button
          onClick={() =>
            setPicked(
              all
                ? {}
                : Object.fromEntries(actions.map((a: any) => [a.key, true]))
            )
          }
          className="text-[11px] text-slate-500 hover:text-slate-300 underline shrink-0"
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
              onClick={() => setPicked((p) => ({ ...p, [action.key]: !on }))}
              title={action.description}
              className={cn(
                "flex items-start gap-2.5 text-left rounded-xl border px-3 py-2.5 transition-all",
                on
                  ? "bg-red-500/10 border-red-500/40"
                  : "bg-[#0a1628] border-slate-800 hover:border-slate-700"
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
                    "block text-[12px] font-bold",
                    on ? "text-white" : "text-slate-400"
                  )}
                >
                  {action.label}
                </span>
                <span className="block text-[10px] text-slate-600 leading-relaxed">
                  {action.description}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      <p
        className={cn(
          "text-[11px] leading-relaxed",
          count === 0 ? "text-slate-600" : "text-amber-200/70"
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
          className="px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-400 hover:text-white disabled:opacity-40 transition-all"
        >
          Abbrechen
        </button>
        <button
          onClick={() => onSave(picked)}
          disabled={busy}
          className="flex-1 py-2.5 rounded-xl bg-primary text-xs font-black uppercase tracking-widest hover:brightness-110 disabled:opacity-40 transition-all"
        >
          Speichern
        </button>
      </div>
    </div>
  );
}

export function AntiNukePanel({ guildId }: { guildId: string }) {
  const load = useCallback(() => api.getAntiNuke(guildId), [guildId]);
  const p = usePanel(load);
  const [adding, setAdding] = useState(false);
  const [newUser, setNewUser] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [showModules, setShowModules] = useState(false);

  if (p.loading) return <Loading />;

  const status = !!p.data?.status;
  const actions: any[] = p.data?.actions || [];
  const whitelist: any[] = p.data?.whitelist || [];

  return (
    <section className="space-y-5">
      <Warnings items={p.data?.warnings} />

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
              : "bg-[#0d1b31] border-slate-800"
          )}
        >
          <div className="min-w-0">
            <p
              className={cn(
                "font-black",
                status ? "text-emerald-300" : "text-slate-400"
              )}
            >
              {status ? "Aktiv" : "Aus"}
            </p>
            <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">
              {status
                ? `${p.data?.module_count ?? 0} Wächter laufen mit.`
                : "Es wird nichts überwacht."}
            </p>
          </div>
          <InlineToggle
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

        <button
          onClick={() => setShowModules((o) => !o)}
          className="w-full flex items-center justify-between px-4 py-3 rounded-xl bg-[#0d1b31] border border-slate-800"
        >
          <span className="text-[11px] font-black uppercase tracking-widest text-slate-500">
            Was genau überwacht wird ({actions.length} Bereiche)
          </span>
          <ChevronDown
            className={cn(
              "h-3.5 w-3.5 text-slate-600 transition-transform",
              showModules && "rotate-180"
            )}
          />
        </button>

        {showModules && (
          <div className="grid sm:grid-cols-2 gap-2">
            {actions.map((action) => (
              <div
                key={action.key}
                className={cn(
                  "rounded-xl border px-3 py-2.5",
                  !action.loaded
                    ? "bg-red-500/[0.05] border-red-500/25"
                    : status
                    ? "bg-[#0d1b31] border-slate-800"
                    : "bg-[#0d1b31]/50 border-slate-800/60"
                )}
              >
                <p
                  className={cn(
                    "text-[12px] font-bold",
                    status && action.loaded ? "text-white" : "text-slate-500"
                  )}
                >
                  {action.label}
                </p>
                <p className="text-[10px] text-slate-600 leading-relaxed mt-0.5">
                  {action.loaded
                    ? action.description
                    : "Dieses Modul ist nicht geladen — es schützt gerade nichts."}
                </p>
              </div>
            ))}
          </div>
        )}

        <p className="text-[11px] text-slate-600 leading-relaxed">
          Die Bereiche lassen sich nicht einzeln abschalten — Anti-Nuke ist
          an oder aus. Wer eine bestimmte Aktion ausführen darf, regelst du
          unten über die Ausnahmeliste.
        </p>
      </Card>

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
            className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-white/[0.03] border border-white/10 text-xs font-black uppercase tracking-widest text-slate-300 hover:text-white transition-all"
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
                await p.act(() =>
                  api.setAntiNukeWhitelist(guildId, newUser, picked)
                );
                setAdding(false);
                setNewUser("");
              }}
            />
          </div>
        )}

        {whitelist.length === 0 ? (
          <p className="text-sm text-slate-500 py-8 text-center border border-dashed border-slate-800 rounded-2xl">
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
                      : "bg-[#0d1b31] border-slate-800"
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
                          <span className="ml-2 px-1.5 py-0.5 rounded bg-primary/15 text-primary text-[9px] font-black uppercase align-middle">
                            Bot
                          </span>
                        )}
                      </p>
                      <p
                        className={cn(
                          "text-[11px] truncate",
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
                          await p.act(() =>
                            api.setAntiNukeWhitelist(guildId, entry.id, picked)
                          );
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

      <Card
        icon={Shield}
        title="Damit der Schutz auch greift"
        subtitle="Drei Dinge, ohne die Anti-Nuke nur zuschaut."
      >
        <div className="space-y-3 text-[12px] text-slate-400 leading-relaxed">
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
    </section>
  );
}
