"use client";

/**
 * Team-Bewerbung über die Website.
 *
 * ── Der Ablauf ──────────────────────────────────────────────────────
 *
 *   1. Rolle wählen — Content Creator, Designer, Moderator, Tester.
 *      Jede hat eigene Fragen.
 *   2. Fragen beantworten. Der Fortschritt steht links.
 *   3. Abschicken. Danach zeigt dieselbe Seite den Stand: Nummer,
 *      Status, Begründung sobald entschieden wurde.
 *
 * ── Warum Discord-Login Pflicht ist ─────────────────────────────────
 *
 * Ohne Anmeldung könnte jeder beliebig viele Bewerbungen abschicken,
 * und niemand wüsste hinterher, wem die Rolle gegeben werden soll.
 * Die Nutzer-ID setzt der Proxy aus der Sitzung ein, nicht der
 * Browser — sonst wäre „eine Bewerbung pro Person“ mit einer
 * erfundenen ID beliebig oft zu umgehen.
 *
 * ── Warum der Fortschritt links steht ───────────────────────────────
 *
 * Sechs bis sieben Fragen sind länger als ein Bildschirm. Ohne
 * Anzeige weiß niemand, ob noch zwei oder noch zehn kommen — und
 * bricht in der Mitte ab.
 */

import React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { signIn, useSession } from "next-auth/react";
import {
  ArrowLeft, ArrowRight, Check, Clock, Loader2, LogIn, Send, X,
} from "lucide-react";
import { toast } from "sonner";
import { SiteNav } from "@/components/site-nav";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Rolle {
  key: string;
  label: string;
  short: string;
  colour: string;
  questions: number;
  question_list: string[];
  open: boolean;
}

const STATUS_TEXT: Record<string, { label: string; ton: string; text: string }> = {
  open: {
    label: "In Prüfung",
    ton: "text-amber-400 border-amber-500/30 bg-amber-500/10",
    text: "Deine Bewerbung liegt beim Team. Bitte hab noch etwas Geduld — wir melden uns per Direktnachricht.",
  },
  accepted: {
    label: "Angenommen",
    ton: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
    text: "Willkommen im Team! Deine Rolle sollte im Support-Server bereits vergeben sein.",
  },
  denied: {
    label: "Abgelehnt",
    ton: "text-red-400 border-red-500/30 bg-red-500/10",
    text: "Diesmal hat es nicht gereicht. Das Team kann deine Bewerbung freigeben, dann darfst du es erneut versuchen.",
  },
  withdrawn: {
    label: "Zurückgezogen",
    ton: "text-slate-400 border-slate-700 bg-slate-800/40",
    text: "Du hast deine Bewerbung zurückgezogen.",
  },
};

export default function ApplyPage() {
  return (
    // useSearchParams verlangt eine Suspense-Grenze, sonst faellt die
    // ganze Seite beim Bauen auf Client-Rendering zurueck.
    <React.Suspense fallback={<div className="min-h-screen bg-[#0a0a0c]" />}>
      <ApplyInner />
    </React.Suspense>
  );
}

function ApplyInner() {
  const { data: session, status: authStatus } = useSession();
  const params = useSearchParams();

  const [rollen, setRollen] = React.useState<Rolle[]>([]);
  const [grenzen, setGrenzen] = React.useState<any>({ min_answer: 10 });
  const [meine, setMeine] = React.useState<any>(null);
  const [laden, setLaden] = React.useState(true);

  const [gewaehlt, setGewaehlt] = React.useState<Rolle | null>(null);
  const [antworten, setAntworten] = React.useState<string[]>([]);
  const [frage, setFrage] = React.useState(0);
  const [sendet, setSendet] = React.useState(false);

  const angemeldet = Boolean(session?.user?.id);

  React.useEffect(() => {
    api
      .getApplyRoles()
      .then((d) => {
        setRollen(d?.roles || []);
        setGrenzen({ min_answer: d?.min_answer ?? 10, max_answer: d?.max_answer });
      })
      .catch(() => {})
      .finally(() => setLaden(false));
  }, []);

  // Die eigene Bewerbung nachschlagen, sobald jemand angemeldet ist.
  React.useEffect(() => {
    if (!session?.user?.id) return;
    api
      .getMyApplication(session.user.id)
      .then((d) => setMeine(d?.application || null))
      .catch(() => {});
  }, [session?.user?.id]);

  // Aus der Navigationsleiste kommt ?rolle=tester -- dann direkt den
  // passenden Fragebogen oeffnen statt erst die Auswahl zu zeigen.
  React.useEffect(() => {
    const wunsch = params.get("rolle");
    if (!wunsch || gewaehlt || meine || rollen.length === 0) return;
    const treffer = rollen.find((r) => r.key === wunsch && r.open);
    if (treffer) {
      setGewaehlt(treffer);
      setAntworten(new Array(treffer.question_list.length).fill(""));
      setFrage(0);
    }
  }, [params, rollen, gewaehlt, meine]);

  const waehlen = (rolle: Rolle) => {
    setGewaehlt(rolle);
    setAntworten(new Array(rolle.question_list.length).fill(""));
    setFrage(0);
  };

  const min = grenzen.min_answer ?? 10;
  const aktuell = antworten[frage] ?? "";
  const langGenug = aktuell.trim().length >= min;
  const fertig =
    gewaehlt !== null &&
    antworten.length === gewaehlt.question_list.length &&
    antworten.every((a) => a.trim().length >= min);

  const abschicken = async () => {
    if (!gewaehlt || !fertig) return;
    setSendet(true);
    try {
      const antwort = await api.submitApplication(gewaehlt.key, antworten);
      setMeine(antwort?.application || null);
      setGewaehlt(null);
      toast.success("Bewerbung abgeschickt.");
    } catch (e: any) {
      // 409 heisst: es gibt schon eine. Der Bot schickt Nummer und
      // Stand mit -- die werden angezeigt statt einer roten
      // Fehlermeldung.
      const d = e?.detail ?? e?.data?.detail;
      if (d?.application) {
        setMeine(d.application);
        setGewaehlt(null);
        toast.info(d.message || "Du hast schon eine Bewerbung laufen.");
      } else {
        toast.error(e?.message || "Das hat nicht geklappt.");
      }
    } finally {
      setSendet(false);
    }
  };

  const zurueckziehen = async () => {
    if (!session?.user?.id) return;
    try {
      await api.withdrawApplication(session.user.id);
      const d = await api.getMyApplication(session.user.id);
      setMeine(d?.application || null);
      toast.success("Zurückgezogen.");
    } catch (e: any) {
      toast.error(e?.message || "Das ging nicht.");
    }
  };

  return (
    <div className="min-h-screen overflow-x-clip bg-[#0a0a0c] text-slate-200">
      <SiteNav />

      <main className="mx-auto max-w-[1100px] px-6 lg:px-12 py-16">
        <Link
          href="/team"
          className="inline-flex items-center gap-2 text-[14px] text-slate-500 hover:text-white transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Zurück zum Team
        </Link>

        <h1 className="mt-6 text-[38px] sm:text-[44px] font-extrabold tracking-tight text-white">
          Team beitreten
        </h1>
        <p className="mt-4 max-w-2xl text-[16px] leading-relaxed text-slate-400">
          Vier Rollen, je eigene Fragen. Beantworte sie in Ruhe — wir
          lesen jede Bewerbung von Hand.
        </p>

        {/* Nicht angemeldet */}
        {authStatus !== "loading" && !angemeldet && (
          <div className="mt-10 rounded-2xl border border-slate-800 bg-[#0f0f13] p-8 text-center">
            <div className="mx-auto mb-4 h-12 w-12 rounded-2xl bg-indigo-500/15 grid place-items-center">
              <LogIn className="h-6 w-6 text-indigo-400" />
            </div>
            <h2 className="text-[20px] font-bold text-white">
              Bitte mit Discord anmelden
            </h2>
            <p className="mx-auto mt-3 max-w-md text-[14px] leading-relaxed text-slate-400">
              Deine Bewerbung wird mit deinem Discord-Konto verknüpft —
              nur so wissen wir, wem wir die Rolle geben. Es gilt eine
              Bewerbung pro Person.
            </p>
            <button
              type="button"
              onClick={() => signIn("discord", { callbackUrl: "/team/apply" })}
              className="mt-6 rounded-xl bg-[#5865f2] px-7 py-3.5 text-[15px] font-semibold text-white hover:bg-[#4752c4] transition-colors"
            >
              Mit Discord anmelden
            </button>
          </div>
        )}

        {/* Es gibt schon eine Bewerbung -> Fortschritt statt Formular */}
        {angemeldet && meine && (
          <div className="mt-10 grid gap-5 lg:grid-cols-[280px_1fr]">
            {/* Links: der Stand */}
            <aside className="rounded-2xl border border-slate-800 bg-[#0f0f13] p-5 h-fit">
              <div className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                Deine Bewerbungsnummer
              </div>
              <div className="mt-2 font-mono text-[22px] font-bold text-white">
                {meine.ticket}
              </div>

              <div
                className={cn(
                  "mt-5 rounded-xl border px-3 py-2 text-[13px] font-semibold",
                  STATUS_TEXT[meine.status]?.ton,
                )}
              >
                {STATUS_TEXT[meine.status]?.label ?? meine.status}
              </div>

              <dl className="mt-5 space-y-3 text-[13px]">
                <div>
                  <dt className="text-slate-600">Rolle</dt>
                  <dd className="text-slate-300">{meine.role_label}</dd>
                </div>
                <div>
                  <dt className="text-slate-600">Eingereicht</dt>
                  <dd className="text-slate-300">
                    {new Date(meine.created_at * 1000).toLocaleDateString("de-DE")}
                  </dd>
                </div>
                {meine.decided_at > 0 && (
                  <div>
                    <dt className="text-slate-600">Entschieden</dt>
                    <dd className="text-slate-300">
                      {new Date(meine.decided_at * 1000).toLocaleDateString("de-DE")}
                    </dd>
                  </div>
                )}
              </dl>

              {meine.status === "open" && (
                <button
                  type="button"
                  onClick={zurueckziehen}
                  className="mt-6 w-full rounded-xl border border-slate-800 px-4 py-2.5 text-[13px] text-slate-400 hover:border-red-500/40 hover:text-red-400 transition-colors"
                >
                  Zurückziehen
                </button>
              )}
            </aside>

            {/* Rechts: Text und die eigenen Antworten */}
            <div className="space-y-5">
              <div className="rounded-2xl border border-slate-800 bg-[#0f0f13] p-6">
                <div className="flex items-start gap-3">
                  <Clock className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
                  <div>
                    <h2 className="text-[18px] font-bold text-white">
                      {meine.status === "open"
                        ? "Bitte hab noch etwas Geduld"
                        : STATUS_TEXT[meine.status]?.label}
                    </h2>
                    <p className="mt-2 text-[14px] leading-relaxed text-slate-400">
                      {STATUS_TEXT[meine.status]?.text}
                    </p>
                    {meine.reason && (
                      <div className="mt-4 rounded-xl border border-slate-800 bg-[#0a0a0c] p-4">
                        <div className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                          Begründung des Teams
                        </div>
                        <p className="mt-1.5 text-[14px] leading-relaxed text-slate-300">
                          {meine.reason}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-800 bg-[#0f0f13] p-6">
                <h3 className="text-[15px] font-bold text-white">
                  Deine Antworten
                </h3>
                <div className="mt-4 space-y-4">
                  {(meine.questions || []).map((f: string, i: number) => (
                    <div key={i}>
                      <div className="text-[13px] font-semibold text-slate-300">
                        {i + 1}. {f}
                      </div>
                      <p className="mt-1 whitespace-pre-wrap text-[13px] leading-relaxed text-slate-500">
                        {meine.answers?.[i] || "—"}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Rollenauswahl */}
        {angemeldet && !meine && !gewaehlt && (
          <div className="mt-10">
            {laden ? (
              <div className="flex justify-center py-16">
                <Loader2 className="h-6 w-6 animate-spin text-indigo-400 opacity-60" />
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                {rollen.map((r) => (
                  <button
                    key={r.key}
                    type="button"
                    disabled={!r.open}
                    onClick={() => waehlen(r)}
                    className={cn(
                      "rounded-2xl border border-slate-800 bg-[#0f0f13] p-6 text-left transition-colors",
                      r.open
                        ? "hover:border-slate-700"
                        : "opacity-50 cursor-not-allowed",
                    )}
                  >
                    <div
                      className="h-2 w-10 rounded-full"
                      style={{ background: r.colour }}
                    />
                    <h3 className="mt-4 text-[19px] font-bold text-white">
                      {r.label}
                    </h3>
                    <p className="mt-1.5 text-[14px] leading-relaxed text-slate-400">
                      {r.short}
                    </p>
                    <p className="mt-4 flex items-center gap-1.5 text-[13px] text-slate-500">
                      {r.open ? (
                        <>
                          {r.questions} Fragen
                          <ArrowRight className="h-3.5 w-3.5" />
                        </>
                      ) : (
                        "Gerade geschlossen"
                      )}
                    </p>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Der Fragebogen */}
        {angemeldet && !meine && gewaehlt && (
          <div className="mt-10 grid gap-5 lg:grid-cols-[280px_1fr]">
            {/* Links: Fortschritt */}
            <aside className="rounded-2xl border border-slate-800 bg-[#0f0f13] p-5 h-fit lg:sticky lg:top-24">
              <div className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                Bewerbung als
              </div>
              <div className="mt-1.5 text-[17px] font-bold text-white">
                {gewaehlt.label}
              </div>

              <div className="mt-5 h-1.5 rounded-full bg-slate-800">
                <div
                  className="h-full rounded-full bg-indigo-500 transition-all"
                  style={{
                    width: `${
                      (antworten.filter((a) => a.trim().length >= min).length /
                        gewaehlt.question_list.length) *
                      100
                    }%`,
                  }}
                />
              </div>
              <div className="mt-2 text-[12px] text-slate-500">
                {antworten.filter((a) => a.trim().length >= min).length} von{" "}
                {gewaehlt.question_list.length} beantwortet
              </div>

              <ol className="mt-5 space-y-1.5">
                {gewaehlt.question_list.map((f, i) => {
                  const ok = (antworten[i] ?? "").trim().length >= min;
                  return (
                    <li key={i}>
                      <button
                        type="button"
                        onClick={() => setFrage(i)}
                        className={cn(
                          "flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left text-[12px] transition-colors",
                          i === frage
                            ? "bg-indigo-500/10 text-indigo-300"
                            : "text-slate-500 hover:bg-white/[0.03]",
                        )}
                      >
                        <span
                          className={cn(
                            "mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border text-[9px]",
                            ok
                              ? "border-emerald-500/40 bg-emerald-500/20 text-emerald-400"
                              : "border-slate-700",
                          )}
                        >
                          {ok ? <Check className="h-2.5 w-2.5" /> : i + 1}
                        </span>
                        <span className="line-clamp-2">{f}</span>
                      </button>
                    </li>
                  );
                })}
              </ol>

              <button
                type="button"
                onClick={() => setGewaehlt(null)}
                className="mt-5 w-full rounded-xl border border-slate-800 px-4 py-2 text-[13px] text-slate-500 hover:text-white hover:border-slate-700 transition-colors"
              >
                Andere Rolle
              </button>
            </aside>

            {/* Rechts: die aktuelle Frage */}
            <div className="rounded-2xl border border-slate-800 bg-[#0f0f13] p-6">
              <div className="text-[12px] text-slate-500">
                Frage {frage + 1} von {gewaehlt.question_list.length}
              </div>
              <h2 className="mt-2 text-[19px] font-bold leading-snug text-white">
                {gewaehlt.question_list[frage]}
              </h2>

              <textarea
                value={aktuell}
                onChange={(e) => {
                  const next = [...antworten];
                  next[frage] = e.target.value;
                  setAntworten(next);
                }}
                rows={8}
                maxLength={grenzen.max_answer ?? 2000}
                placeholder="Deine Antwort …"
                className="mt-5 w-full rounded-xl border border-slate-800 bg-[#0a0a0c] px-4 py-3 text-[15px] leading-relaxed text-white placeholder:text-slate-600 focus:outline-none focus:border-slate-700 transition-colors resize-none"
              />

              <div className="mt-2 flex items-center justify-between text-[12px]">
                <span className={langGenug ? "text-slate-600" : "text-amber-500"}>
                  {langGenug
                    ? `${aktuell.trim().length} Zeichen`
                    : `Noch mindestens ${min - aktuell.trim().length} Zeichen`}
                </span>
                <span className="text-slate-600">
                  max. {grenzen.max_answer ?? 2000}
                </span>
              </div>

              <div className="mt-6 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  disabled={frage === 0}
                  onClick={() => setFrage((f) => Math.max(0, f - 1))}
                  className="rounded-xl border border-slate-800 px-5 py-2.5 text-[14px] text-slate-300 hover:border-slate-700 transition-colors disabled:opacity-40"
                >
                  Zurück
                </button>

                {frage < gewaehlt.question_list.length - 1 ? (
                  <button
                    type="button"
                    onClick={() => setFrage((f) => f + 1)}
                    className="flex items-center gap-2 rounded-xl bg-[#5865f2] px-5 py-2.5 text-[14px] font-semibold text-white hover:bg-[#4752c4] transition-colors"
                  >
                    Weiter
                    <ArrowRight className="h-4 w-4" />
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={!fertig || sendet}
                    onClick={abschicken}
                    className="flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-2.5 text-[14px] font-semibold text-white hover:bg-emerald-700 transition-colors disabled:opacity-40"
                  >
                    {sendet ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Send className="h-4 w-4" />
                    )}
                    Bewerbung abschicken
                  </button>
                )}

                {!fertig && frage === gewaehlt.question_list.length - 1 && (
                  <span className="text-[12px] text-amber-500">
                    Es fehlen noch Antworten — links siehst du welche.
                  </span>
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
