"use client";

/**
 * Der Cookie-Hinweis als Fenster in der Bildschirmmitte.
 *
 * ── Was vorher war ──────────────────────────────────────────────────
 *
 * Nichts. Es gab keinen Hinweis — der Screenshot, der ihn als Leiste
 * am unteren Rand zeigt, stammt von einer anderen Seite. Gebaut ist
 * er hier so, wie der Nutzer ihn wollte: beim Betreten der Startseite
 * mittig, alles dahinter abgedunkelt und unscharf.
 *
 * ── Warum er nicht sofort dasteht ───────────────────────────────────
 *
 * Der Server weiß nicht, ob dieser Browser schon bestätigt hat, ohne
 * das Cookie zu lesen — und die Startseite ist statisch. Also
 * entscheidet der Browser: erst rendern, dann prüfen, dann einblenden.
 * Ohne diesen Umweg blitzt das Fenster bei jedem Aufruf kurz auf, auch
 * bei jemandem, der es längst weggeklickt hat.
 *
 * Deshalb steht `bereit` neben `offen`: **erst gemessen, dann
 * angezeigt.** Ein einziger Zustand hätte genau das Aufblitzen
 * erzeugt, das er verhindern soll.
 *
 * ── Warum das Speichern das Schließen nicht aufhält ─────────────────
 *
 * Der Klick auf „Verstanden“ schließt sofort und schickt den Nachweis
 * nebenher. Andersherum — erst warten, dann schließen — hinge das
 * Fenster bei einem langsamen Netz sekundenlang, und bei einem
 * Serverfehler für immer. Ein Hinweisfenster, das sich nicht schließen
 * lässt, weil ein Protokolleintrag scheitert, ist schlimmer als ein
 * fehlender Protokolleintrag.
 *
 * Damit trotzdem nichts verloren geht, merkt sich der Browser die
 * Bestätigung im Cookie **bevor** die Anfrage rausgeht, und ein
 * fehlgeschlagener Versuch wird beim nächsten Besuch nachgeholt
 * (`nachtragen`).
 *
 * ── Barrierefreiheit ────────────────────────────────────────────────
 *
 * `role="dialog"`, `aria-modal`, der Fokus wandert beim Öffnen auf den
 * Knopf und bleibt im Fenster gefangen, Escape schließt. Ein Fenster,
 * das den Rest der Seite sperrt, muss mit der Tastatur bedienbar sein
 * — sonst sperrt es Leute aus, die keine Maus benutzen.
 */

import React from "react";
import Link from "next/link";
import { ChevronDown, Cookie, ShieldCheck } from "lucide-react";
import { useSession } from "next-auth/react";

import {
  BESUCHER_COOKIE,
  COOKIES,
  HINWEIS_COOKIE,
  HINWEIS_TAGE,
  HINWEIS_VERSION,
  besucherId,
  leseCookie,
  setzeCookie,
} from "@/lib/cookie-consent";

/** Was im Cookie steht, wenn eine Bestätigung noch nicht angekommen ist. */
const OFFEN_SUFFIX = ":offen";

export function CookieHinweis() {
  const { data: session } = useSession();

  // Zwei Zustände, nicht einer: `bereit` heißt „das Cookie ist
  // gelesen". Ohne diese Trennung blitzt das Fenster bei jedem Aufruf
  // kurz auf, bevor der Browser merkt, dass längst bestätigt wurde.
  const [bereit, setBereit] = React.useState(false);
  const [offen, setOffen] = React.useState(false);
  const [details, setDetails] = React.useState(false);

  const fenster = React.useRef<HTMLDivElement>(null);
  const knopf = React.useRef<HTMLButtonElement>(null);

  /**
   * Den Nachweis abschicken.
   *
   * `keepalive`: der Klick schließt das Fenster, und wer sofort
   * weiterklickt, bricht sonst die eigene Anfrage ab. Mit dem Flag
   * schickt der Browser sie auch dann noch zu Ende.
   *
   * Die Discord-ID hängt der Proxy aus der Sitzung an; hier wird sie
   * bewusst nicht mitgeschickt. Ein Wert aus dem Browser wäre kein
   * Nachweis, sondern eine Behauptung.
   */
  const melden = React.useCallback(async (kennung: string) => {
    try {
      const antwort = await fetch("/api/bot/cookies/consent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        keepalive: true,
        body: JSON.stringify({
          besucher_id: kennung,
          version: HINWEIS_VERSION,
          pfad: window.location.pathname,
        }),
      });
      if (!antwort.ok) return false;
      // Erst jetzt gilt die Bestätigung als angekommen. Der Merker
      // fällt weg, damit der nächste Besuch nichts nachträgt.
      setzeCookie(HINWEIS_COOKIE, HINWEIS_VERSION, HINWEIS_TAGE);
      return true;
    } catch {
      // Kein Netz, Bot aus, Wartung: alles derselbe Fall. Das Cookie
      // behält sein `:offen`, und der nächste Besuch versucht es noch
      // einmal.
      return false;
    }
  }, []);

  // ── Beim Betreten: gab es schon eine Bestätigung? ──────────────────
  React.useEffect(() => {
    const stand = leseCookie(HINWEIS_COOKIE);

    if (!stand || !stand.startsWith(HINWEIS_VERSION)) {
      // Nichts da, oder der Text hat sich geändert.
      setOffen(true);
      setBereit(true);
      return;
    }

    setBereit(true);

    // Bestätigt, aber der Nachweis kam nie an. Still nachholen: das
    // Fenster ein zweites Mal zu zeigen wäre die falsche Antwort auf
    // ein Problem, das der Besucher nicht verursacht hat.
    if (stand.endsWith(OFFEN_SUFFIX)) {
      const kennung = leseCookie(BESUCHER_COOKIE);
      if (kennung) void melden(kennung);
    }
  }, [melden]);

  /**
   * Ein zweites Mal melden, sobald sich jemand anmeldet.
   *
   * Ohne das trüge der Nachweis für alle, die den Hinweis vor dem
   * Login wegklicken, nie eine Discord-ID — und das ist die Reihenfolge,
   * in der es fast immer passiert: Startseite, Hinweis, dann anmelden.
   * Der Speicher aktualisiert die vorhandene Zeile, es entsteht also
   * keine zweite.
   */
  React.useEffect(() => {
    if (!bereit || offen) return;
    const konto = (session?.user as { id?: string } | undefined)?.id;
    if (!konto) return;

    const stand = leseCookie(HINWEIS_COOKIE);
    if (!stand.startsWith(HINWEIS_VERSION)) return;

    const kennung = leseCookie(BESUCHER_COOKIE);
    if (kennung) void melden(kennung);
    // Absichtlich nur an der Konto-ID hängend: `session` ist bei jedem
    // Rendern ein neues Objekt und löste sonst eine Anfrage pro Render
    // aus.
  }, [bereit, offen, session?.user, melden]);

  const bestaetigen = React.useCallback(() => {
    const kennung = besucherId();

    // Erst merken, dann schließen, dann melden. Diese Reihenfolge
    // entscheidet: bräche der Browser zwischen Klick und Antwort weg,
    // stünde die Bestätigung trotzdem im Cookie -- mit dem Merker, dass
    // der Nachweis noch aussteht.
    setzeCookie(HINWEIS_COOKIE, `${HINWEIS_VERSION}${OFFEN_SUFFIX}`, HINWEIS_TAGE);
    setOffen(false);

    void melden(kennung);
  }, [melden]);

  // ── Tastatur: Escape schließt, Tab bleibt im Fenster ───────────────
  React.useEffect(() => {
    if (!offen) return;

    // Der Fokus muss ins Fenster wandern, sonst tabbt sich jemand ohne
    // Maus durch die Seite dahinter, die er gar nicht bedienen kann.
    knopf.current?.focus();

    const aufTaste = (ereignis: KeyboardEvent) => {
      if (ereignis.key === "Escape") {
        // Escape ist hier dasselbe wie „Verstanden": der Hinweis ist
        // eine Information, kein Antrag. Ihn ungelesen wegzudrücken
        // muss möglich sein, ohne dass er beim nächsten Aufruf wieder
        // dasteht.
        bestaetigen();
        return;
      }
      if (ereignis.key !== "Tab") return;

      const ziele = fenster.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled])',
      );
      if (!ziele || ziele.length === 0) return;

      const erstes = ziele[0];
      const letztes = ziele[ziele.length - 1];

      if (ereignis.shiftKey && document.activeElement === erstes) {
        ereignis.preventDefault();
        letztes.focus();
      } else if (!ereignis.shiftKey && document.activeElement === letztes) {
        ereignis.preventDefault();
        erstes.focus();
      }
    };

    document.addEventListener("keydown", aufTaste);

    // Hinter dem Fenster darf nicht gescrollt werden: sonst wandert die
    // Seite unter dem Hinweis weg und er steht über einem Inhalt, zu
    // dem er nicht mehr gehört.
    const vorher = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", aufTaste);
      document.body.style.overflow = vorher;
    };
  }, [offen, bestaetigen]);

  if (!bereit || !offen) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="cookie-hinweis-titel"
      aria-describedby="cookie-hinweis-text"
    >
      {/* Die abgedunkelte, unscharfe Fläche dahinter. Kein onClick:
          ein Klick daneben darf nichts bestätigen -- man klickt daneben,
          weil man das Fenster wegwischen will, nicht weil man zustimmt. */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-md"
        aria-hidden="true"
      />

      <div
        ref={fenster}
        className="relative w-full max-w-lg rounded-3xl border border-slate-800 bg-[#131318] p-6 shadow-2xl shadow-black/60 sm:p-7"
      >
        <div className="flex items-start gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-indigo-500/20 bg-indigo-500/10">
            <Cookie className="h-6 w-6 text-indigo-400" />
          </div>
          <div className="min-w-0">
            <h2
              id="cookie-hinweis-titel"
              className="text-lg font-bold text-white"
            >
              Nur technisch notwendige Cookies
            </h2>
            <p
              id="cookie-hinweis-text"
              className="mt-2 text-[14px] leading-relaxed text-slate-400"
            >
              Diese Website setzt ausschließlich Cookies, die für Anmeldung
              und Sicherheit gebraucht werden. Kein Tracking, keine Werbung,
              keine Weitergabe an Dritte.
            </p>
          </div>
        </div>

        {/* Details: die tatsächliche Liste. Zugeklappt, weil sie sechs
            Zeilen lang ist -- aber vorhanden, weil „nur notwendige“
            ohne Beleg eine Behauptung bleibt. */}
        <button
          type="button"
          onClick={() => setDetails((zustand) => !zustand)}
          aria-expanded={details}
          className="mt-5 flex w-full items-center justify-between rounded-xl border border-slate-800 bg-[#0f0f13] px-4 py-3 text-[13px] font-semibold text-slate-300 transition-colors hover:border-slate-700 hover:text-white"
        >
          <span className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-slate-500" />
            Details — welche Cookies genau?
          </span>
          <ChevronDown
            className={
              "h-4 w-4 shrink-0 text-slate-500 transition-transform " +
              (details ? "rotate-180" : "")
            }
          />
        </button>

        {details && (
          <div className="mt-3 max-h-56 space-y-2 overflow-y-auto rounded-xl border border-slate-800 bg-[#0e0e12] p-3">
            {COOKIES.map((eintrag) => (
              <div
                key={eintrag.name}
                className="rounded-lg border border-slate-800/70 bg-[#131318] p-3"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <code className="text-[12px] font-semibold text-indigo-300">
                    {eintrag.name}
                  </code>
                  {/* Kein `uppercase`: „30 Tage“ ist eine Angabe, keine
                      Rubrik. Mit Versalien stand dort „30 TAGE“ -- und
                      damit etwas anderes als in der
                      Datenschutzerklärung, die dieselbe Laufzeit
                      nennt. Im Browser-Test aufgefallen, nicht im
                      Quelltext. */}
                  <span className="text-[11px] font-semibold tracking-wide text-slate-500">
                    {eintrag.dauer}
                  </span>
                </div>
                <p className="mt-1.5 text-[12px] leading-relaxed text-slate-400">
                  {eintrag.zweck}
                </p>
              </div>
            ))}
            <p className="px-1 pt-1 text-[12px] leading-relaxed text-slate-500">
              Alle davon sind technisch notwendig — für sie ist nach
              § 25 Abs. 2 TDDDG keine Einwilligung nötig. Deshalb gibt es
              hier auch keinen Ablehnen-Knopf: er würde nichts abschalten
              können, ohne die Anmeldung mit abzuschalten.
            </p>
          </div>
        )}

        <div className="mt-6 flex flex-col-reverse items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Link
            href="/privacy"
            className="text-[13px] text-slate-500 underline decoration-slate-700 underline-offset-4 transition-colors hover:text-slate-300"
          >
            Datenschutzerklärung
          </Link>
          <button
            ref={knopf}
            type="button"
            onClick={bestaetigen}
            className="rounded-xl bg-[#5865f2] px-6 py-3 text-[14px] font-bold text-white transition-colors hover:bg-[#4752c4] focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-2 focus-visible:ring-offset-[#131318]"
          >
            Verstanden
          </button>
        </div>
      </div>
    </div>
  );
}
