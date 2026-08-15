"use client";

/**
 * Team-Bewerbung über die Website.
 *
 * ── Der Ablauf ──────────────────────────────────────────────────────
 *
 *   1. Rolle wählen.
 *   2. Alle Fragen auf einer Seite beantworten — nicht eine nach der
 *      anderen. Wer bei Frage 5 merkt, dass Frage 2 besser passt,
 *      soll zurückspringen können, ohne zu klicken.
 *   3. Abschicken. Danach zeigt dieselbe Seite den Stand.
 *
 * ── Was gegenüber der ersten Fassung anders ist ─────────────────────
 *
 * Die erste Fassung zeigte eine Frage pro Bildschirm mit Weiter- und
 * Zurück-Knopf. Das las sich wie ein Behördenformular: man sah nie,
 * was noch kommt, und für einen Blick auf die vorige Antwort musste
 * man zweimal klicken. Jetzt stehen alle Fragen untereinander, die
 * Leiste links springt hin.
 *
 * Neu außerdem: der Entwurf überlebt einen Reload (localStorage),
 * jede Frage sagt beim Tippen, ob sie lang genug ist, und beim
 * Abschicken wird zur ersten unfertigen Frage gesprungen statt nur
 * „es fehlt etwas“ zu melden.
 *
 * ── Warum Discord-Login Pflicht ist ─────────────────────────────────
 *
 * Ohne Anmeldung könnte jeder beliebig viele Bewerbungen abschicken,
 * und niemand wüsste hinterher, wem die Rolle gegeben werden soll.
 * Die Nutzer-ID setzt der Proxy aus der Sitzung ein, nicht der
 * Browser.
 */

import React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { signIn, useSession } from "next-auth/react";
import {
  ArrowLeft, Check, CheckCircle2, Clock, Loader2, LogIn, Send, Shield,
  Sparkles, Video, Wrench, X,
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

/** Ein Symbol je Rolle — vier farbige Punkte sagen weniger als vier Bilder. */
const ROLLEN_ICON: Record<string, any> = {
  content: Video,
  designer: Sparkles,
  moderator: Shield,
  tester: Wrench,
};

const STATUS_TEXT: Record<
  string,
  { label: string; ton: string; icon: any; text: string }
> = {
  open: {
    label: "In Prüfung",
    ton: "text-amber-400 border-amber-500/30 bg-amber-500/10",
    icon: Clock,
    text: "Deine Bewerbung liegt beim Team. Bitte hab noch etwas Geduld — wir melden uns per Direktnachricht, sobald wir sie gelesen haben.",
  },
  accepted: {
    label: "Angenommen",
    ton: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
    icon: CheckCircle2,
    text: "Willkommen im Team! Deine Rolle sollte im Server bereits vergeben sein.",
  },
  denied: {
    label: "Abgelehnt",
    ton: "text-red-400 border-red-500/30 bg-red-500/10",
    icon: X,
    text: "Diesmal hat es nicht gereicht. Das Team kann deine Bewerbung freigeben — dann darfst du es erneut versuchen.",
  },
  withdrawn: {
    label: "Zurückgezogen",
    ton: "text-slate-400 border-slate-700 bg-slate-800/40",
    icon: X,
    text: "Du hast deine Bewerbung zurückgezogen. Melde dich beim Team, wenn du es doch noch einmal versuchen möchtest.",
  },
};

const CARD = "rounded-2xl border border-slate-800 bg-[#0f0f13]";

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
  const [sendet, setSendet] = React.useState(false);
  /** Welche Frage gerade im Blick ist — für die Leiste links. */
  const [imBlick, setImBlick] = React.useState(0);
  /** Erst nach dem ersten Absenden rot markieren. */
  const [gepruept, setGepruept] = React.useState(false);

  const felder = React.useRef<Array<HTMLTextAreaElement | null>>([]);
  const angemeldet = Boolean(session?.user?.id);
  const min = grenzen.min_answer ?? 10;
  /** Wie viele Rollen wirklich offen sind — gezaehlt, nicht behauptet. */
  const offeneRollen = rollen.filter((r) => r.open).length;

  React.useEffect(() => {
    api
      .getApplyRoles()
      .then((d) => {
        setRollen(d?.roles || []);
        setGrenzen({
          min_answer: d?.min_answer ?? 10,
          max_answer: d?.max_answer ?? 2000,
        });
      })
      .catch(() => {})
      .finally(() => setLaden(false));
  }, []);

  React.useEffect(() => {
    if (!session?.user?.id) return;
    api
      .getMyApplication(session.user.id)
      .then((d) => setMeine(d?.application || null))
      .catch(() => {});
  }, [session?.user?.id]);

  /** Wo der Entwurf liegt. Je Rolle einer. */
  const entwurfSchluessel = (key: string) => `bewerbung-entwurf-${key}`;

  const waehlen = React.useCallback((rolle: Rolle) => {
    // Einen begonnenen Entwurf wiederherstellen. Sechs Fragen sind
    // eine halbe Stunde Arbeit -- die darf ein versehentlicher
    // Reload nicht kosten.
    let start = new Array(rolle.question_list.length).fill("");
    try {
      const roh = localStorage.getItem(entwurfSchluessel(rolle.key));
      if (roh) {
        const gespeichert = JSON.parse(roh);
        if (
          Array.isArray(gespeichert) &&
          gespeichert.length === rolle.question_list.length
        ) {
          start = gespeichert.map((x: any) => String(x ?? ""));
        }
      }
    } catch {
      // Kaputter Eintrag: dann eben leer anfangen.
    }
    setGewaehlt(rolle);
    setAntworten(start);
    setImBlick(0);
    setGepruept(false);
  }, []);

  // Aus der Navigationsleiste kommt ?rolle=tester.
  React.useEffect(() => {
    const wunsch = params.get("rolle");
    if (!wunsch || gewaehlt || meine || rollen.length === 0) return;
    const treffer = rollen.find((r) => r.key === wunsch && r.open);
    if (treffer) waehlen(treffer);
  }, [params, rollen, gewaehlt, meine, waehlen]);

  // Den Entwurf sichern, mit kurzer Pause statt bei jedem Zeichen.
  React.useEffect(() => {
    if (!gewaehlt) return;
    const t = setTimeout(() => {
      try {
        localStorage.setItem(
          entwurfSchluessel(gewaehlt.key),
          JSON.stringify(antworten),
        );
      } catch {
        // Privater Modus, voller Speicher -- kein Grund für eine
        // Fehlermeldung mitten im Ausfüllen.
      }
    }, 600);
    return () => clearTimeout(t);
  }, [antworten, gewaehlt]);

  const fertigeAnzahl = antworten.filter((a) => a.trim().length >= min).length;
  const fertig =
    gewaehlt !== null &&
    antworten.length === gewaehlt.question_list.length &&
    fertigeAnzahl === gewaehlt.question_list.length;

  const springeZu = (i: number) => {
    setImBlick(i);
    felder.current[i]?.focus();
    felder.current[i]?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const abschicken = async () => {
    if (!gewaehlt) return;
    if (!fertig) {
      setGepruept(true);
      const erste = antworten.findIndex((a) => a.trim().length < min);
      if (erste >= 0) {
        springeZu(erste);
        toast.error(`Frage ${erste + 1} braucht noch eine Antwort.`);
      }
      return;
    }
    setSendet(true);
    try {
      const antwort = await api.submitApplication(gewaehlt.key, antworten);
      try {
        localStorage.removeItem(entwurfSchluessel(gewaehlt.key));
      } catch {
        // egal
      }
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

      <main className="mx-auto max-w-[1100px] px-6 lg:px-12 py-14">
        <Link
          href="/team"
          className="inline-flex items-center gap-2 text-[14px] text-slate-500 transition-colors hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" />
          Zurück zum Team
        </Link>

        <h1 className="mt-6 text-[36px] sm:text-[42px] font-extrabold tracking-tight text-white">
          Team beitreten
        </h1>
        {/* Die Anzahl wird gezaehlt, nicht behauptet. Hier stand fest
            „Vier Rollen" -- eine Zahl, die falsch wird, sobald das Team
            im Admin-Bereich eine Rolle schliesst. Solange die Liste
            noch laedt, steht die Zahl gar nicht da: eine kurz
            aufblitzende Null waere schlimmer als eine Luecke. */}
        <p className="mt-3 max-w-2xl text-[16px] leading-relaxed text-slate-400">
          {laden
            ? "Je Rolle eigene Fragen."
            : offeneRollen === 1
              ? "Eine offene Rolle mit eigenen Fragen."
              : `${offeneRollen} offene Rollen, je eigene Fragen.`}{" "}
          Lass dir Zeit — dein Entwurf bleibt erhalten, auch wenn du die
          Seite schließt.
        </p>

        {/* ── Nicht angemeldet ──────────────────────────── */}
        {authStatus !== "loading" && !angemeldet && (
          <div className={cn(CARD, "mt-9 p-8 text-center")}>
            <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-indigo-500/15">
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
            <div className="mt-6 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <button
                type="button"
                onClick={() => signIn("discord", { callbackUrl: "/team/apply" })}
                className="rounded-xl bg-[#5865f2] px-7 py-3.5 text-[15px] font-semibold text-white transition-colors hover:bg-[#4752c4]"
              >
                Mit Discord anmelden
              </button>
              {/* Ein Ausweg, der vorher fehlte. Wer hier ohne Konto
                  landete, sah eine Seite, die „Rollen" verspricht und
                  keine einzige zeigt -- und die einzige Antwort darauf
                  war „melde dich an, dann erfaehrst du wofuer". Die
                  Uebersicht auf /team braucht keinen Login. */}
              <Link
                href="/team"
                className="rounded-xl border border-slate-800 bg-[#0e0e12] px-6 py-3.5 text-[15px] font-semibold text-slate-300 transition-colors hover:border-slate-700 hover:text-white"
              >
                Erst die Rollen ansehen
              </Link>
            </div>
          </div>
        )}

        {/* ── Es gibt schon eine Bewerbung ──────────────── */}
        {angemeldet && meine && (
          <div className="mt-9 grid gap-4 lg:grid-cols-[300px_1fr]">
            <aside className={cn(CARD, "h-fit p-5")}>
              <div className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                Deine Bewerbungsnummer
              </div>
              <div className="mt-2 font-mono text-[24px] font-bold text-white">
                {meine.ticket}
              </div>

              <div
                className={cn(
                  "mt-5 flex items-center gap-2 rounded-xl border px-3 py-2 text-[13px] font-semibold",
                  STATUS_TEXT[meine.status]?.ton,
                )}
              >
                {React.createElement(
                  STATUS_TEXT[meine.status]?.icon ?? Clock,
                  { className: "h-4 w-4" },
                )}
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
                  className="mt-6 w-full rounded-xl border border-slate-800 px-4 py-2.5 text-[13px] text-slate-400 transition-colors hover:border-red-500/40 hover:text-red-400"
                >
                  Zurückziehen
                </button>
              )}
            </aside>

            <div className="space-y-4">
              <div className={cn(CARD, "p-6")}>
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

              <div className={cn(CARD, "p-6")}>
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

        {/* ── Rollenauswahl ─────────────────────────────── */}
        {angemeldet && !meine && !gewaehlt && (
          <div className="mt-9">
            {laden ? (
              <div className="flex justify-center py-16">
                <Loader2 className="h-6 w-6 animate-spin text-indigo-400 opacity-60" />
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {rollen.map((r) => {
                  const Icon = ROLLEN_ICON[r.key] || Sparkles;
                  return (
                    <button
                      key={r.key}
                      type="button"
                      disabled={!r.open}
                      onClick={() => waehlen(r)}
                      className={cn(
                        "rounded-2xl border border-slate-800 bg-[#0f0f13] p-5 text-left transition-colors",
                        r.open
                          ? "hover:border-slate-700"
                          : "cursor-not-allowed opacity-50",
                      )}
                    >
                      <div className="flex items-center gap-3">
                        <span
                          className="grid h-10 w-10 shrink-0 place-items-center rounded-xl"
                          style={{ background: `${r.colour}22` }}
                        >
                          <Icon className="h-5 w-5" style={{ color: r.colour }} />
                        </span>
                        <h3 className="text-[17px] font-bold text-white">
                          {r.label}
                        </h3>
                      </div>
                      <p className="mt-3 text-[14px] leading-relaxed text-slate-400">
                        {r.short}
                      </p>
                      <p className="mt-3 text-[13px] text-slate-500">
                        {r.open
                          ? `${r.questions} Fragen · etwa 15 Minuten`
                          : "Gerade geschlossen"}
                      </p>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* ── Der Fragebogen ────────────────────────────── */}
        {angemeldet && !meine && gewaehlt && (
          <div className="mt-9 grid gap-4 lg:grid-cols-[260px_1fr]">
            {/* Leiste links: Fortschritt und Sprungmarken. */}
            <aside className={cn(CARD, "h-fit p-5 lg:sticky lg:top-24")}>
              <div className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                Bewerbung als
              </div>
              <div className="mt-1.5 text-[17px] font-bold text-white">
                {gewaehlt.label}
              </div>

              <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-slate-800">
                <div
                  className="h-full rounded-full bg-indigo-500 transition-all duration-300"
                  style={{
                    width: `${(fertigeAnzahl / gewaehlt.question_list.length) * 100}%`,
                  }}
                />
              </div>
              <div className="mt-2 text-[12px] text-slate-500">
                {fertigeAnzahl} von {gewaehlt.question_list.length} beantwortet
              </div>

              <ol className="mt-5 space-y-1">
                {gewaehlt.question_list.map((f, i) => {
                  const ok = (antworten[i] ?? "").trim().length >= min;
                  return (
                    <li key={i}>
                      <button
                        type="button"
                        onClick={() => springeZu(i)}
                        className={cn(
                          "flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left text-[12px] transition-colors",
                          i === imBlick
                            ? "bg-white/[0.06] text-slate-200"
                            : "text-slate-500 hover:bg-white/[0.03]",
                        )}
                      >
                        <span
                          className={cn(
                            "mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border text-[9px]",
                            ok
                              ? "border-emerald-500/40 bg-emerald-500/20 text-emerald-400"
                              : gepruept
                                ? "border-amber-500/40 text-amber-500"
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
                className="mt-5 w-full rounded-xl border border-slate-800 px-4 py-2 text-[13px] text-slate-500 transition-colors hover:border-slate-700 hover:text-white"
              >
                Andere Rolle
              </button>
              <p className="mt-2.5 text-[11px] leading-relaxed text-slate-600">
                Dein Entwurf wird gespeichert — du kannst jederzeit
                weitermachen.
              </p>
            </aside>

            {/* Alle Fragen untereinander. */}
            <div className="space-y-3">
              {gewaehlt.question_list.map((frage, i) => {
                const wert = antworten[i] ?? "";
                const ok = wert.trim().length >= min;
                const fehlt = gepruept && !ok;
                return (
                  <div
                    key={i}
                    className={cn(
                      CARD,
                      "p-5 transition-colors",
                      fehlt && "border-amber-500/40",
                    )}
                  >
                    <label className="block">
                      <span className="flex items-start gap-2.5">
                        <span
                          className={cn(
                            "mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border text-[11px] font-bold",
                            ok
                              ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-400"
                              : "border-slate-700 text-slate-500",
                          )}
                        >
                          {ok ? <Check className="h-3 w-3" /> : i + 1}
                        </span>
                        <span className="text-[16px] font-semibold leading-snug text-white">
                          {frage}
                        </span>
                      </span>

                      <textarea
                        ref={(el) => {
                          felder.current[i] = el;
                        }}
                        value={wert}
                        onFocus={() => setImBlick(i)}
                        onChange={(e) => {
                          const next = [...antworten];
                          next[i] = e.target.value;
                          setAntworten(next);
                        }}
                        rows={4}
                        maxLength={grenzen.max_answer ?? 2000}
                        placeholder="Deine Antwort …"
                        className="mt-3 w-full resize-y rounded-xl border border-slate-800 bg-[#0a0a0c] px-4 py-3 text-[15px] leading-relaxed text-white placeholder:text-slate-600 transition-colors focus:border-slate-700 focus:outline-none"
                      />
                    </label>

                    <div className="mt-1.5 flex items-center justify-between text-[12px]">
                      <span
                        className={cn(
                          ok
                            ? "text-slate-600"
                            : fehlt
                              ? "text-amber-500"
                              : "text-slate-500",
                        )}
                      >
                        {ok
                          ? `${wert.trim().length} Zeichen`
                          : `Noch mindestens ${min - wert.trim().length} Zeichen`}
                      </span>
                      <span className="text-slate-700">
                        {wert.length} / {grenzen.max_answer ?? 2000}
                      </span>
                    </div>
                  </div>
                );
              })}

              {/* Abschicken */}
              <div className={cn(CARD, "flex flex-wrap items-center gap-4 p-5")}>
                <button
                  type="button"
                  disabled={sendet}
                  onClick={abschicken}
                  className={cn(
                    "flex items-center gap-2 rounded-xl px-6 py-3 text-[15px] font-semibold text-white transition-colors",
                    fertig
                      ? "bg-emerald-600 hover:bg-emerald-700"
                      : "bg-slate-800 hover:bg-slate-700",
                    sendet && "opacity-50",
                  )}
                >
                  {sendet ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-4 w-4" />
                  )}
                  Bewerbung abschicken
                </button>

                <p className="min-w-0 flex-1 text-[13px] text-slate-500">
                  {fertig
                    ? "Alles ausgefüllt. Nach dem Abschicken kannst du hier deinen Stand verfolgen."
                    : `Es fehlen noch ${
                        gewaehlt.question_list.length - fertigeAnzahl
                      } Antworten — beim Klick springen wir zur ersten.`}
                </p>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
