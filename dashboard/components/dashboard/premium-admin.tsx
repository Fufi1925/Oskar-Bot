"use client";

/**
 * Premium — der Admin-Bereich.
 *
 * ── Was hier vorher stand ───────────────────────────────────────────
 *
 * Eine Liste von **Keys**. Das war die falsche Einheit: ein Konto kann
 * mehrere Keys haben (verlängert, nachgelegt, ausgeglichen), und dann
 * stand dieselbe Person dreimal da — einmal abgelaufen, zweimal
 * gültig. Wer wissen wollte „hat diese Person Premium und bis wann“,
 * musste die Zeilen im Kopf zusammenrechnen.
 *
 * Dazu kam: seit der Zusammenlegung werden gar keine Keys mehr
 * ausgegeben. Premium kommt aus dem Beta-Antrag. Ein Reiter, dessen
 * Hauptfunktion „Key prägen“ ist, zeigt damit auf einen Weg, den
 * niemand mehr geht.
 *
 * ── Was jetzt hier steht ────────────────────────────────────────────
 *
 * Eine Liste von **Konten**. Eine Zeile je Person, mit dem Datum, das
 * auch sie selbst im Dashboard sieht. Sortiert nach „läuft als
 * Nächstes ab“ — das ist die Frage, wegen der man den Reiter öffnet.
 *
 * Die Zahlen oben sind keine Zierde: „läuft bald ab“ ist die einzige,
 * bei der man handeln muss, und sie steht deshalb zuerst und in Gold.
 *
 * Die Key-Verwaltung ist nicht verschwunden, sondern in einen eigenen
 * Abschnitt gewandert, den man aufklappt. Bestehende Keys müssen
 * sperrbar bleiben — aber sie sind nicht mehr der Alltag.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, Ban, CheckCircle2, ChevronDown, Clock, Crown, Gift,
  Infinity as InfinityIcon, KeyRound, Plus, RefreshCw, Search,
  Sparkles, Timer, Users, X,
} from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CountUp, Reveal } from "@/components/ui/reveal";
import { PremiumTrials } from "@/components/dashboard/premium-trials";
import { PremiumKeys } from "@/components/dashboard/premium-keys";

/* ── Typen ─────────────────────────────────────────────────────────── */

interface Konto {
  user_id: string;
  user_name: string;
  avatar: string;
  premium: boolean;
  lifetime: boolean;
  expires_at: number | null;
  duration_days: number;
  since: number | null;
  keys_total: number;
  keys_active: number;
  revoked: number;
  note: string;
  via_trial: boolean;
  source: string;
}

type Filter = "alle" | "aktiv" | "bald" | "probewoche" | "beendet";

/* ── Hilfen ────────────────────────────────────────────────────────── */

const INPUT =
  "w-full bg-[#0e0e12] border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-white " +
  "placeholder:text-slate-600 focus:border-primary/50 focus:outline-none transition-colors";

const CARD = "bg-[#131318] border border-slate-800 rounded-3xl";

/** Deutsche Schreibweise. `toFixed`/`toString` liefern einen Punkt. */
function datum(sekunden?: number | null): string {
  if (!sekunden) return "—";
  return new Date(sekunden * 1000).toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

/** Verbleibende Tage. `null`, wenn es nie abläuft. */
function tageUebrig(sekunden?: number | null): number | null {
  if (!sekunden) return null;
  return Math.max(0, Math.ceil((sekunden * 1000 - Date.now()) / 86_400_000));
}

/** Läuft in den nächsten sieben Tagen ab. Dieselbe Grenze wie im Bot. */
function laeuftBaldAb(k: Konto): boolean {
  if (!k.premium || k.lifetime || !k.expires_at) return false;
  const uebrig = tageUebrig(k.expires_at);
  return uebrig !== null && uebrig <= 7;
}

function Zahl({
  icon: Icon,
  wert,
  label,
  ton = "normal",
}: {
  icon: any;
  wert: number;
  label: string;
  ton?: "normal" | "gold" | "still";
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border p-4",
        ton === "gold"
          ? "border-amber-400/30 bg-amber-400/[0.06]"
          : "border-slate-800 bg-[#0f0f13]"
      )}
    >
      <div className="flex items-center gap-2">
        <Icon
          className={cn(
            "h-3.5 w-3.5",
            ton === "gold"
              ? "text-amber-400"
              : ton === "still"
                ? "text-slate-600"
                : "text-primary"
          )}
        />
        <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">
          {label}
        </span>
      </div>
      <div
        className={cn(
          "mt-1 text-2xl font-black tabular-nums",
          ton === "gold" ? "text-amber-300" : "text-white"
        )}
      >
        <CountUp value={wert} />
      </div>
    </div>
  );
}

/* ── Der Reiter ────────────────────────────────────────────────────── */

export function PremiumAdmin() {
  const [konten, setKonten] = useState<Konto[]>([]);
  const [zahlen, setZahlen] = useState<any>(null);
  const [laedt, setLaedt] = useState(true);
  const [beschaeftigt, setBeschaeftigt] = useState(false);

  const [filter, setFilter] = useState<Filter>("alle");
  const [suche, setSuche] = useState("");
  const [offen, setOffen] = useState<string | null>(null);

  // Das Vergabe-Formular. Zu, bis man es braucht: vergeben wird
  // selten, nachgesehen ständig.
  const [zeigeVergabe, setZeigeVergabe] = useState(false);
  const [empfaenger, setEmpfaenger] = useState("");
  const [tage, setTage] = useState("30");
  const [notiz, setNotiz] = useState("");

  // Die Key-Verwaltung. Ebenfalls zu: seit der Zusammenlegung werden
  // keine neuen Keys mehr ausgegeben, bestehende müssen aber
  // sperrbar bleiben.
  const [zeigeKeys, setZeigeKeys] = useState(false);

  const laden = useCallback(async (still = false) => {
    if (!still) setLaedt(true);
    try {
      const antwort = await api.listPremiumAccounts(300);
      setKonten(antwort?.accounts ?? []);
      setZahlen(antwort?.stats ?? null);
    } catch (err: any) {
      toast.error(err?.message || "Die Konten ließen sich nicht laden.");
    } finally {
      setLaedt(false);
    }
  }, []);

  useEffect(() => {
    laden();
  }, [laden]);

  const gefiltert = useMemo(() => {
    const suchbegriff = suche.trim().toLowerCase();
    return konten.filter((k) => {
      if (filter === "aktiv" && !k.premium) return false;
      if (filter === "bald" && !laeuftBaldAb(k)) return false;
      if (filter === "probewoche" && !(k.premium && k.via_trial)) return false;
      if (filter === "beendet" && k.premium) return false;

      if (!suchbegriff) return true;
      return (
        k.user_id.includes(suchbegriff) ||
        (k.user_name || "").toLowerCase().includes(suchbegriff) ||
        (k.note || "").toLowerCase().includes(suchbegriff)
      );
    });
  }, [konten, filter, suche]);

  const vergeben = async () => {
    const id = empfaenger.trim();
    if (!/^\d{15,25}$/.test(id)) {
      toast.error("Das sieht nicht nach einer Discord-ID aus.");
      return;
    }
    const t = Number(tage);
    if (!Number.isFinite(t) || t < 0) {
      toast.error("Die Laufzeit muss eine Zahl sein. 0 heißt unbegrenzt.");
      return;
    }

    setBeschaeftigt(true);
    try {
      await api.grantPremiumAccount(id, t, notiz.trim());
      toast.success(
        t === 0
          ? "Premium vergeben — unbegrenzt."
          : `Premium vergeben — ${t} Tage.`
      );
      setEmpfaenger("");
      setNotiz("");
      setZeigeVergabe(false);
      await laden(true);
    } catch (err: any) {
      toast.error(err?.message || "Das Vergeben ist fehlgeschlagen.");
    } finally {
      setBeschaeftigt(false);
    }
  };

  const entziehen = async (k: Konto) => {
    const name = k.user_name || k.user_id;
    if (
      !window.confirm(
        `${name} verliert damit Premium — auf beiden Bots.\n\n` +
          "Eine laufende Probewoche wird ebenfalls beendet."
      )
    ) {
      return;
    }

    setBeschaeftigt(true);
    try {
      const res = await api.revokePremiumAccount(k.user_id);
      toast.success(
        res?.trial_ended
          ? "Premium entzogen, Probewoche beendet."
          : "Premium entzogen."
      );
      await laden(true);
    } catch (err: any) {
      toast.error(err?.message || "Das Entziehen ist fehlgeschlagen.");
    } finally {
      setBeschaeftigt(false);
    }
  };

  const FILTER: Array<{ id: Filter; label: string }> = [
    { id: "alle", label: "Alle" },
    { id: "aktiv", label: "Mit Premium" },
    { id: "bald", label: "Läuft bald ab" },
    { id: "probewoche", label: "Probewoche" },
    { id: "beendet", label: "Beendet" },
  ];

  return (
    <div className="space-y-5">
      {/* ── Die Zahlen ──────────────────────────────────────────── */}
      <Reveal>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          {/* Zuerst und in Gold: die einzige Zahl, bei der man etwas
              tun muss. */}
          <Zahl
            icon={Timer}
            wert={zahlen?.expiring_soon ?? 0}
            label="Läuft bald ab"
            ton="gold"
          />
          <Zahl icon={Crown} wert={zahlen?.active ?? 0} label="Mit Premium" />
          <Zahl
            icon={InfinityIcon}
            wert={zahlen?.lifetime ?? 0}
            label="Unbegrenzt"
          />
          <Zahl icon={Gift} wert={zahlen?.trials ?? 0} label="Probewoche" />
          <Zahl
            icon={Users}
            wert={zahlen?.expired ?? 0}
            label="Beendet"
            ton="still"
          />
        </div>
      </Reveal>

      {/* ── Werkzeugleiste ──────────────────────────────────────── */}
      <Reveal>
        <div className={cn(CARD, "p-4")}>
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
              <input
                value={suche}
                onChange={(e) => setSuche(e.target.value)}
                placeholder="Name, Konto-ID oder Notiz"
                className={cn(INPUT, "pl-10")}
                aria-label="Konten durchsuchen"
              />
            </div>

            <div className="flex flex-wrap gap-1.5">
              {FILTER.map((f) => (
                <button
                  key={f.id}
                  onClick={() => setFilter(f.id)}
                  className={cn(
                    "rounded-xl px-3 py-2 text-xs font-bold transition",
                    filter === f.id
                      ? "bg-primary text-white"
                      : "border border-slate-800 bg-[#0f0f13] text-slate-400 hover:bg-white/[0.04]"
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => laden()}
                disabled={laedt}
                className="rounded-xl border border-slate-800 bg-[#0f0f13] p-2.5 text-slate-400 transition hover:bg-white/[0.04] disabled:opacity-40"
                title="Neu laden"
              >
                <RefreshCw className={cn("h-4 w-4", laedt && "animate-spin")} />
              </button>
              <button
                onClick={() => setZeigeVergabe((v) => !v)}
                className="inline-flex items-center gap-2 rounded-xl bg-amber-400 px-4 py-2.5 text-xs font-bold text-black transition hover:brightness-110"
              >
                {zeigeVergabe ? (
                  <X className="h-3.5 w-3.5" />
                ) : (
                  <Plus className="h-3.5 w-3.5" />
                )}
                Premium vergeben
              </button>
            </div>
          </div>

          {/* Das Vergabe-Formular. */}
          {zeigeVergabe && (
            <div className="mt-4 space-y-3 rounded-2xl border border-amber-400/25 bg-amber-400/[0.04] p-4">
              <p className="text-xs leading-relaxed text-slate-400">
                Der übliche Weg ist der Beta-Antrag. Hier vergibst du
                Premium von Hand — für Support-Fälle und Zusagen außerhalb
                des Formulars. Es gilt sofort für{" "}
                <strong className="text-slate-300">beide Bots</strong>.
              </p>

              <div className="grid gap-3 sm:grid-cols-3">
                <div className="sm:col-span-2">
                  <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500">
                    Discord-ID
                  </label>
                  <input
                    value={empfaenger}
                    onChange={(e) => setEmpfaenger(e.target.value)}
                    placeholder="1303627964734246944"
                    className={cn(INPUT, "mt-1.5")}
                    inputMode="numeric"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500">
                    Tage — 0 = unbegrenzt
                  </label>
                  <input
                    value={tage}
                    onChange={(e) => setTage(e.target.value)}
                    className={cn(INPUT, "mt-1.5")}
                    inputMode="numeric"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500">
                  Notiz — warum
                </label>
                <input
                  value={notiz}
                  onChange={(e) => setNotiz(e.target.value)}
                  placeholder="z. B. Ausgleich für den Ausfall am 12."
                  className={cn(INPUT, "mt-1.5")}
                />
              </div>

              <button
                onClick={vergeben}
                disabled={beschaeftigt || !empfaenger.trim()}
                className="inline-flex items-center gap-2 rounded-xl bg-amber-400 px-4 py-2.5 text-xs font-bold text-black transition hover:brightness-110 disabled:opacity-40"
              >
                <Sparkles className="h-3.5 w-3.5" />
                Vergeben
              </button>
            </div>
          )}
        </div>
      </Reveal>

      {/* ── Die Liste ───────────────────────────────────────────── */}
      <Reveal>
        <div className={cn(CARD, "overflow-hidden")}>
          <div className="flex items-center justify-between border-b border-slate-800 bg-[#0f0f13] px-5 py-3">
            <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">
              {gefiltert.length}{" "}
              {gefiltert.length === 1 ? "Konto" : "Konten"}
            </span>
            <span className="text-[10px] text-slate-600">
              Was zuerst abläuft, steht oben
            </span>
          </div>

          {laedt ? (
            <div className="space-y-2 p-4">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="h-16 animate-pulse rounded-2xl bg-[#0f0f13]"
                />
              ))}
            </div>
          ) : gefiltert.length === 0 ? (
            <div className="px-5 py-12 text-center">
              <div className="mx-auto mb-3 w-fit rounded-2xl bg-[#0f0f13] p-3">
                <Crown className="h-5 w-5 text-slate-700" />
              </div>
              <p className="text-sm font-bold text-slate-400">
                {suche || filter !== "alle"
                  ? "Nichts gefunden."
                  : "Noch hat niemand Premium."}
              </p>
              {!suche && filter === "alle" && (
                <p className="mt-1 text-xs text-slate-600">
                  Sobald ein Beta-Antrag angenommen wird, steht die Person
                  hier.
                </p>
              )}
            </div>
          ) : (
            gefiltert.map((k, i) => {
              const uebrig = tageUebrig(k.expires_at);
              const bald = laeuftBaldAb(k);
              const auf = offen === k.user_id;

              return (
                <div
                  key={k.user_id}
                  className={cn(i > 0 && "border-t border-slate-800")}
                >
                  <button
                    onClick={() => setOffen(auf ? null : k.user_id)}
                    className="flex w-full items-center gap-3 px-5 py-3.5 text-left transition hover:bg-white/[0.02]"
                  >
                    {/* Bild */}
                    <div className="h-9 w-9 shrink-0 overflow-hidden rounded-full border border-slate-800 bg-[#0f0f13]">
                      {k.avatar ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={k.avatar}
                          alt=""
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center">
                          <Users className="h-4 w-4 text-slate-700" />
                        </div>
                      )}
                    </div>

                    {/* Name */}
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="truncate text-sm font-bold text-white">
                          {k.user_name || "Unbekannt"}
                        </span>
                        {k.premium ? (
                          k.lifetime ? (
                            <span className="rounded-md border border-amber-400/20 bg-amber-400/10 px-1.5 py-0.5 text-[9px] font-black uppercase tracking-widest text-amber-400">
                              Unbegrenzt
                            </span>
                          ) : k.via_trial ? (
                            <span className="rounded-md border border-sky-500/20 bg-sky-500/10 px-1.5 py-0.5 text-[9px] font-black uppercase tracking-widest text-sky-300">
                              Probewoche
                            </span>
                          ) : (
                            <span className="rounded-md border border-emerald-500/20 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-black uppercase tracking-widest text-emerald-300">
                              Aktiv
                            </span>
                          )
                        ) : (
                          <span className="rounded-md border border-slate-600/20 bg-slate-500/10 px-1.5 py-0.5 text-[9px] font-black uppercase tracking-widest text-slate-500">
                            Beendet
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 truncate font-mono text-[11px] text-slate-600">
                        {k.user_id}
                      </div>
                    </div>

                    {/* Ablauf */}
                    <div className="shrink-0 text-right">
                      {k.premium ? (
                        k.lifetime ? (
                          <span className="text-xs text-slate-500">
                            läuft nicht ab
                          </span>
                        ) : (
                          <>
                            <div
                              className={cn(
                                "text-xs font-bold tabular-nums",
                                bald ? "text-amber-300" : "text-slate-300"
                              )}
                            >
                              {uebrig} {uebrig === 1 ? "Tag" : "Tage"}
                            </div>
                            <div className="text-[10px] text-slate-600">
                              bis {datum(k.expires_at)}
                            </div>
                          </>
                        )
                      ) : (
                        <span className="text-xs text-slate-600">—</span>
                      )}
                    </div>

                    <ChevronDown
                      className={cn(
                        "h-4 w-4 shrink-0 text-slate-600 transition-transform",
                        auf && "rotate-180"
                      )}
                    />
                  </button>

                  {/* Aufgeklappt */}
                  {auf && (
                    <div className="space-y-3 border-t border-slate-800 bg-[#0f0f13] px-5 py-4">
                      <div className="grid gap-3 text-xs sm:grid-cols-3">
                        <div>
                          <div className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                            Seit
                          </div>
                          <div className="mt-0.5 text-slate-300">
                            {datum(k.since)}
                          </div>
                        </div>
                        <div>
                          <div className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                            Laufzeit
                          </div>
                          <div className="mt-0.5 text-slate-300">
                            {k.lifetime
                              ? "unbegrenzt"
                              : k.duration_days
                                ? `${k.duration_days} Tage`
                                : "—"}
                          </div>
                        </div>
                        <div>
                          <div className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                            Lizenzen
                          </div>
                          <div className="mt-0.5 text-slate-300">
                            {k.keys_active} aktiv
                            {k.revoked > 0 && (
                              <span className="text-slate-600">
                                {" "}
                                · {k.revoked} gesperrt
                              </span>
                            )}
                            {k.keys_total === 0 && k.via_trial && (
                              <span className="text-slate-600">
                                nur Probewoche
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      {k.note && (
                        <div>
                          <div className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                            Notiz
                          </div>
                          <div className="mt-0.5 text-xs text-slate-400">
                            {k.note}
                          </div>
                        </div>
                      )}

                      {k.premium && (
                        <button
                          onClick={() => entziehen(k)}
                          disabled={beschaeftigt}
                          className="inline-flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-3.5 py-2 text-xs font-bold text-red-300 transition hover:bg-red-500/20 disabled:opacity-40"
                        >
                          <Ban className="h-3.5 w-3.5" />
                          Premium entziehen
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </Reveal>

      {/* ── Probewochen ─────────────────────────────────────────── */}
      <Reveal>
        <PremiumTrials />
      </Reveal>

      {/* ── Keys: zugeklappt ────────────────────────────────────── */}
      <Reveal>
        <div className={cn(CARD, "overflow-hidden")}>
          <button
            onClick={() => setZeigeKeys((v) => !v)}
            className="flex w-full items-center gap-3 px-5 py-4 text-left transition hover:bg-white/[0.02]"
          >
            <div className="rounded-xl bg-[#0f0f13] p-2">
              <KeyRound className="h-4 w-4 text-slate-500" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-bold text-white">
                Lizenz-Keys
              </div>
              <div className="mt-0.5 text-xs text-slate-500">
                Aus der Zeit vor der Zusammenlegung. Neue werden nicht mehr
                ausgegeben — bestehende bleiben sperrbar.
              </div>
            </div>
            <ChevronDown
              className={cn(
                "h-4 w-4 shrink-0 text-slate-600 transition-transform",
                zeigeKeys && "rotate-180"
              )}
            />
          </button>

          {zeigeKeys && (
            <div className="border-t border-slate-800 p-4">
              <PremiumKeys />
            </div>
          )}
        </div>
      </Reveal>
    </div>
  );
}
