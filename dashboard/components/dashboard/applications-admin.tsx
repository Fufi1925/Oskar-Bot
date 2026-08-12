"use client";

/**
 * Team-Bewerbungen im Admin-Dashboard.
 *
 * Links die Liste, rechts die gewählte Bewerbung mit allen Antworten
 * und den zwei Knöpfen. Beide Entscheidungen verlangen eine
 * Begründung — sie geht dem Bewerber per Direktnachricht zu, und
 * „abgelehnt“ ohne ein Wort dazu ist keine Antwort.
 *
 * **Warum Annehmen die Rolle gleich mitvergibt:** sonst sind es zwei
 * Schritte, und der zweite wird vergessen. Welche Discord-Rolle je
 * Bewerbungsrolle vergeben wird, steht unten in den Einstellungen.
 * Scheitert das Vergeben — Rolle zu hoch, Person nicht auf dem
 * Server —, bleibt die Entscheidung trotzdem stehen und der Grund
 * wird angezeigt statt verschluckt.
 */

import React from "react";
import {
  AlertTriangle, Check, Clock, Inbox, Loader2, RotateCcw, Settings2, X,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { InlineToggle } from "@/components/dashboard/form-elements";

const CARD = "rounded-2xl border border-slate-800 bg-[#0f0f13] p-5";
const INPUT =
  "w-full rounded-xl border border-slate-800 bg-[#0a0a0c] px-4 py-3 text-[14px] " +
  "text-white placeholder:text-slate-600 focus:outline-none focus:border-slate-700 " +
  "transition-colors";

const STATUS: Record<string, { label: string; ton: string }> = {
  open: { label: "Offen", ton: "text-amber-400 bg-amber-500/10 border-amber-500/30" },
  accepted: { label: "Angenommen", ton: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30" },
  denied: { label: "Abgelehnt", ton: "text-red-400 bg-red-500/10 border-red-500/30" },
  withdrawn: { label: "Zurückgezogen", ton: "text-slate-400 bg-slate-800/50 border-slate-700" },
};

export function ApplicationsAdmin() {
  const [liste, setListe] = React.useState<any[]>([]);
  const [zahlen, setZahlen] = React.useState<any>({});
  const [gewaehlt, setGewaehlt] = React.useState<any>(null);
  const [filter, setFilter] = React.useState("open");
  const [laden, setLaden] = React.useState(true);
  const [busy, setBusy] = React.useState("");
  const [grund, setGrund] = React.useState("");
  const [config, setConfig] = React.useState<any>(null);
  const [zeigeConfig, setZeigeConfig] = React.useState(false);

  const laden_ = React.useCallback(async () => {
    try {
      const d = await api.listApplications(filter);
      setListe(d?.applications || []);
      setZahlen(d?.counts || {});
    } catch (e: any) {
      toast.error(e?.message || "Die Bewerbungen ließen sich nicht laden.");
    } finally {
      setLaden(false);
    }
  }, [filter]);

  React.useEffect(() => {
    laden_();
  }, [laden_]);

  React.useEffect(() => {
    api.getApplyConfig().then(setConfig).catch(() => {});
  }, []);

  const entscheiden = async (status: "accepted" | "denied") => {
    if (!gewaehlt) return;
    if (!grund.trim()) {
      toast.error("Bitte eine Begründung angeben — sie geht dem Bewerber zu.");
      return;
    }
    setBusy(status);
    try {
      const a = await api.decideApplication2(gewaehlt.user_id, status, grund);
      toast.success(
        status === "accepted" ? "Angenommen." : "Abgelehnt.",
      );
      if (a?.role_problem) {
        toast.warning(`Rolle nicht vergeben: ${a.role_problem}`);
      }
      if (a?.dm_delivered === false) {
        toast.warning("Die Direktnachricht kam nicht an (DMs geschlossen).");
      }
      setGewaehlt(null);
      setGrund("");
      await laden_();
    } catch (e: any) {
      toast.error(e?.message || "Das hat nicht geklappt.");
    } finally {
      setBusy("");
    }
  };

  const freigeben = async (userId: string) => {
    setBusy("reopen");
    try {
      await api.reopenApplication(userId);
      toast.success("Freigegeben — die Person darf sich erneut bewerben.");
      setGewaehlt(null);
      await laden_();
    } catch (e: any) {
      toast.error(e?.message || "Das ging nicht.");
    } finally {
      setBusy("");
    }
  };

  const configSpeichern = async (change: any) => {
    const vorher = config;
    setConfig({ ...config, ...change });
    try {
      await api.saveApplyConfig(change);
    } catch (e: any) {
      toast.error(e?.message || "Nicht gespeichert.");
      setConfig(vorher);
    }
  };

  if (laden) {
    return (
      <div className={cn(CARD, "flex justify-center py-16")}>
        <Loader2 className="h-6 w-6 animate-spin text-indigo-400 opacity-60" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Zahlen und Filter */}
      <div className="flex flex-wrap items-center gap-2">
        {[
          { id: "open", label: "Offen" },
          { id: "accepted", label: "Angenommen" },
          { id: "denied", label: "Abgelehnt" },
          { id: "", label: "Alle" },
        ].map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => {
              setFilter(f.id);
              setGewaehlt(null);
            }}
            className={cn(
              "rounded-lg border px-3.5 py-2 text-[13px] transition-colors",
              filter === f.id
                ? "border-indigo-500/40 bg-indigo-500/10 text-indigo-300"
                : "border-slate-800 bg-[#131318] text-slate-400 hover:border-slate-700",
            )}
          >
            {f.label}
            {f.id && zahlen[f.id] > 0 && (
              <span className="ml-1.5 text-slate-600">{zahlen[f.id]}</span>
            )}
          </button>
        ))}

        <button
          type="button"
          onClick={() => setZeigeConfig((z) => !z)}
          className="ml-auto flex items-center gap-2 rounded-lg border border-slate-800 bg-[#131318] px-3.5 py-2 text-[13px] text-slate-400 hover:border-slate-700 transition-colors"
        >
          <Settings2 className="h-3.5 w-3.5" />
          Einstellungen
        </button>
      </div>

      {/* Einstellungen */}
      {zeigeConfig && config && (
        <div className={cn(CARD, "space-y-4")}>
          <h3 className="text-[15px] font-bold text-white">
            Welche Rolle eine Annahme vergibt
          </h3>
          <p className="text-[13px] text-slate-500">
            Je Bewerbungsrolle ein eigener Server und eine eigene Rolle —
            Tester etwa auf den Test-Server, Moderatoren auf den
            Support-Server. Wer nur einen Server hat, lässt das Feld leer
            und stellt ihn unten einmal ein. Ohne Server wird keine Rolle
            vergeben; die Bewerbung lässt sich trotzdem annehmen.
          </p>

          <div className="grid gap-3 sm:grid-cols-2">
            {(config.role_catalog || []).map((r: any) => {
              // Welcher Server fuer diese Rolle gilt: der eigene,
              // sonst der allgemeine. Der Bot rechnet dasselbe aus
              // (`guild_for`) und schickt das Ergebnis mit -- hier
              // wird es nur angezeigt, nicht ein zweites Mal
              // hergeleitet.
              const eigen = config.roles?.[r.key]?.guild_id || "";
              const ziel = config.effective_guild?.[r.key] || "";
              const rollenDesServers = ziel
                ? config.roles_by_guild?.[ziel] || []
                : config.available_roles || [];
              const zielName =
                (config.guilds || []).find((g: any) => g.id === ziel)?.name || "";

              return (
                <div
                  key={r.key}
                  className="rounded-xl bg-[#0a0a0c] border border-slate-800 p-3.5"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[14px] font-semibold text-white">
                      {r.label}
                    </span>
                    <InlineToggle
                      checked={config.roles?.[r.key]?.open ?? true}
                      onCheckedChange={(v) =>
                        configSpeichern({
                          roles: {
                            ...config.roles,
                            [r.key]: { ...config.roles?.[r.key], open: v },
                          },
                        })
                      }
                      label=""
                    />
                  </div>

                  <label className="mt-3 block">
                    <span className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                      Server
                    </span>
                    <select
                      value={eigen}
                      onChange={(e) =>
                        configSpeichern({
                          roles: {
                            ...config.roles,
                            [r.key]: {
                              ...config.roles?.[r.key],
                              guild_id: e.target.value,
                              // Die bisherige Rolle gehoert zum alten
                              // Server und gibt es dort nicht mehr.
                              discord_role_id: "",
                            },
                          },
                        })
                      }
                      className={cn(INPUT, "mt-1.5 py-2 text-[13px]")}
                    >
                      <option value="">
                        Allgemeiner Server
                        {zielName && !eigen ? ` (${zielName})` : ""}
                      </option>
                      {(config.guilds || []).map((g: any) => (
                        <option key={g.id} value={g.id}>
                          {g.name}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="mt-2.5 block">
                    <span className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                      Rolle
                    </span>
                    <select
                      value={config.roles?.[r.key]?.discord_role_id || ""}
                      onChange={(e) =>
                        configSpeichern({
                          roles: {
                            ...config.roles,
                            [r.key]: {
                              ...config.roles?.[r.key],
                              discord_role_id: e.target.value,
                            },
                          },
                        })
                      }
                      disabled={!ziel}
                      className={cn(INPUT, "mt-1.5 py-2 text-[13px]")}
                    >
                      <option value="">Keine Rolle vergeben</option>
                      {rollenDesServers.map((ar: any) => (
                        <option key={ar.id} value={ar.id} disabled={!ar.assignable}>
                          {ar.name}
                          {!ar.assignable ? " (steht über dem Bot)" : ""}
                        </option>
                      ))}
                    </select>
                  </label>

                  {!ziel && (
                    <p className="mt-2 text-[11px] text-amber-500">
                      Kein Server gewählt — es wird keine Rolle vergeben.
                    </p>
                  )}
                </div>
              );
            })}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                Allgemeiner Server
              </span>
              <select
                value={config.guild_id || ""}
                onChange={(e) => configSpeichern({ guild_id: e.target.value })}
                className={cn(INPUT, "mt-2")}
              >
                <option value="">Keiner</option>
                {(config.guilds || []).map((g: any) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </select>
              <span className="mt-1.5 block text-[11px] text-slate-500">
                Gilt für jede Rolle ohne eigenen Server.
              </span>
            </label>
            <label className="block">
              <span className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                Kanal für neue Bewerbungen
              </span>
              <select
                value={config.channel_id || ""}
                onChange={(e) => configSpeichern({ channel_id: e.target.value })}
                className={cn(INPUT, "mt-2")}
              >
                <option value="">Keine Meldung</option>
                {(config.available_channels || []).map((c: any) => (
                  <option key={c.id} value={c.id}>
                    #{c.name}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <InlineToggle
            checked={Boolean(config.dm_applicant)}
            onCheckedChange={(v) => configSpeichern({ dm_applicant: v })}
            label="Bewerber per Direktnachricht über die Entscheidung informieren"
            hint="Geschlossene DMs sind kein Fehler — die Entscheidung gilt trotzdem."
          />
        </div>
      )}

      {/* Liste und Detail */}
      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <div className="space-y-2">
          {liste.length === 0 ? (
            <div className={cn(CARD, "text-center py-12")}>
              <Inbox className="mx-auto h-8 w-8 text-slate-700" />
              <p className="mt-3 text-[14px] text-slate-500">
                Keine Bewerbungen in dieser Ansicht.
              </p>
            </div>
          ) : (
            liste.map((a) => (
              <button
                key={a.user_id}
                type="button"
                onClick={() => {
                  setGewaehlt(a);
                  setGrund("");
                }}
                className={cn(
                  "w-full rounded-xl border p-3.5 text-left transition-colors",
                  gewaehlt?.user_id === a.user_id
                    ? "border-indigo-500/40 bg-indigo-500/5"
                    : "border-slate-800 bg-[#0f0f13] hover:border-slate-700",
                )}
              >
                <div className="flex items-center gap-2.5">
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ background: a.role_colour }}
                  />
                  <span className="min-w-0 flex-1 truncate text-[14px] font-semibold text-white">
                    {a.user_name || a.user_id}
                  </span>
                  <span
                    className={cn(
                      "shrink-0 rounded-md border px-1.5 py-0.5 text-[10px] font-bold",
                      STATUS[a.status]?.ton,
                    )}
                  >
                    {STATUS[a.status]?.label}
                  </span>
                </div>
                <div className="mt-1.5 flex items-center justify-between text-[12px] text-slate-500">
                  <span>{a.role_label}</span>
                  <span className="font-mono text-slate-600">{a.ticket}</span>
                </div>
              </button>
            ))
          )}
        </div>

        {/* Detail */}
        <div>
          {!gewaehlt ? (
            <div className={cn(CARD, "flex items-center justify-center py-20")}>
              <p className="text-[14px] text-slate-500">
                Links eine Bewerbung wählen.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className={CARD}>
                <div className="flex flex-wrap items-start gap-3">
                  <div className="min-w-0 flex-1">
                    <h3 className="text-[19px] font-bold text-white">
                      {gewaehlt.user_name || "Unbekannt"}
                    </h3>
                    <p className="mt-1 text-[13px] text-slate-500">
                      {gewaehlt.role_label} &middot;{" "}
                      <span className="font-mono">{gewaehlt.ticket}</span>{" "}
                      &middot; ID {gewaehlt.user_id}
                    </p>
                    <p className="mt-0.5 text-[12px] text-slate-600">
                      Eingereicht am{" "}
                      {new Date(gewaehlt.created_at * 1000).toLocaleString("de-DE")}
                    </p>
                  </div>
                  <span
                    className={cn(
                      "rounded-lg border px-2.5 py-1 text-[12px] font-bold",
                      STATUS[gewaehlt.status]?.ton,
                    )}
                  >
                    {STATUS[gewaehlt.status]?.label}
                  </span>
                </div>

                {gewaehlt.reason && (
                  <div className="mt-4 rounded-xl border border-slate-800 bg-[#0a0a0c] p-3.5">
                    <div className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                      Begründung von{" "}
                      {gewaehlt.decided_by_name || gewaehlt.decided_by || "—"}
                    </div>
                    <p className="mt-1 text-[13px] leading-relaxed text-slate-300">
                      {gewaehlt.reason}
                    </p>
                  </div>
                )}
              </div>

              <div className={CARD}>
                <h4 className="text-[14px] font-bold text-white">Antworten</h4>
                <div className="mt-4 space-y-4">
                  {(gewaehlt.questions || []).map((f: string, i: number) => (
                    <div key={i}>
                      <div className="text-[13px] font-semibold text-slate-300">
                        {i + 1}. {f}
                      </div>
                      <p className="mt-1 whitespace-pre-wrap text-[13px] leading-relaxed text-slate-500">
                        {gewaehlt.answers?.[i] || "—"}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              {gewaehlt.status === "open" ? (
                <div className={cn(CARD, "space-y-3")}>
                  <label className="block">
                    <span className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                      Begründung (Pflicht — geht dem Bewerber zu)
                    </span>
                    <textarea
                      value={grund}
                      onChange={(e) => setGrund(e.target.value)}
                      rows={3}
                      maxLength={1000}
                      placeholder="Was die Person dazu erfährt …"
                      className={cn(INPUT, "mt-2 resize-none")}
                    />
                  </label>

                  <div className="flex flex-wrap gap-3">
                    <button
                      type="button"
                      disabled={Boolean(busy)}
                      onClick={() => entscheiden("accepted")}
                      className="flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-2.5 text-[14px] font-semibold text-white hover:bg-emerald-700 transition-colors disabled:opacity-40"
                    >
                      {busy === "accepted" ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Check className="h-4 w-4" />
                      )}
                      Annehmen &amp; Rolle geben
                    </button>
                    <button
                      type="button"
                      disabled={Boolean(busy)}
                      onClick={() => entscheiden("denied")}
                      className="flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-5 py-2.5 text-[14px] font-semibold text-red-400 hover:bg-red-500/20 transition-colors disabled:opacity-40"
                    >
                      {busy === "denied" ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <X className="h-4 w-4" />
                      )}
                      Ablehnen
                    </button>
                  </div>
                </div>
              ) : (
                <div className={cn(CARD, "flex flex-wrap items-center gap-3")}>
                  <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400" />
                  <p className="min-w-0 flex-1 text-[13px] text-slate-400">
                    Entschieden. Freigeben löscht die Bewerbung — die Person
                    darf sich danach erneut bewerben.
                  </p>
                  <button
                    type="button"
                    disabled={Boolean(busy)}
                    onClick={() => freigeben(gewaehlt.user_id)}
                    className="flex items-center gap-2 rounded-xl border border-slate-800 px-4 py-2 text-[13px] text-slate-300 hover:border-slate-700 transition-colors disabled:opacity-40"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    Freigeben
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
