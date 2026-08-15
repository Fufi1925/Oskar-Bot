/**
 * Der Cookie-Hinweis: Text, Version und die Liste dessen, was wirklich
 * gesetzt wird.
 *
 * ── Warum das hier steht und nicht im Fenster ───────────────────────
 *
 * Drei Stellen brauchen dieselben Angaben: das Fenster selbst, die
 * Datenschutzerklärung und der Nachweis in der Datenbank. Stünden sie
 * dreimal getrennt, könnte das Fenster „zwei Cookies“ sagen, während
 * die Datenschutzerklärung drei aufzählt — und der Nachweis eine
 * Version festhält, die es nie gab.
 *
 * ── Warum die Liste stimmen muss ────────────────────────────────────
 *
 * Sie ist keine Dekoration. Wer „Details“ aufklappt, liest eine
 * Aussage darüber, was sein Browser bekommt; eine falsche Angabe dort
 * ist genau die Sorte, die nach einem Vorfall zählt. Jeder Eintrag
 * unten steht deshalb wirklich im Code:
 *
 *   next-auth.session-token   `lib/auth.ts`, NextAuth, 30 Tage
 *   next-auth.csrf-token      NextAuth, Schutz vor fremden Formularen
 *   next-auth.callback-url    NextAuth, wohin es nach dem Login geht
 *   wartung_bypass            `lib/maintenance.ts`, 8 Stunden
 *   ub_cookie_hinweis         dieses Fenster, ein Jahr
 *
 * Ein Test vergleicht die Liste mit dem Quelltext. Ein Cookie, das
 * gesetzt wird und hier fehlt, lässt ihn fehlschlagen.
 *
 * ── Warum es keinen „Ablehnen“-Knopf gibt ───────────────────────────
 *
 * Weil er nichts täte. Alle fünf sind technisch notwendig: ohne
 * Sitzungs-Cookie gibt es keine Anmeldung, ohne CSRF-Cookie keine
 * abgesicherten Formulare, und ohne das letzte käme das Fenster bei
 * jedem Seitenaufruf wieder. Für solche Cookies verlangt § 25 Abs. 2
 * TDDDG gar keine Einwilligung. Ein Knopf, der „ablehnen“ verspricht
 * und dann doch alles setzt, wäre eine Lüge in Knopfform — stattdessen
 * steht offen da, was Sache ist, und der Weg hinaus ist die Seite zu
 * verlassen.
 */

/**
 * Die Fassung des Hinweistextes.
 *
 * Sie wandert mit in den Nachweis. Ändert sich der Text wesentlich,
 * wird die Zahl erhöht — dann ist später zu sehen, wem welcher Text
 * gezeigt wurde, statt nur „hat irgendwann irgendetwas bestätigt“.
 */
export const HINWEIS_VERSION = "2026-08-1";

/** Der Name des Cookies, in dem die Bestätigung im Browser steht. */
export const HINWEIS_COOKIE = "ub_cookie_hinweis";

/** Die Browser-Kennung, die zusammen mit der Bestätigung gespeichert wird. */
export const BESUCHER_COOKIE = "ub_besucher";

/**
 * Wie lange die Bestätigung im Browser gilt: ein Jahr.
 *
 * Länger wäre unehrlich — nach einem Jahr weiß niemand mehr, was er
 * bestätigt hat. Der Nachweis in der Datenbank hält etwas länger
 * (`KEEP_DAYS = 400`), damit er die Bestätigung überdauert und nicht
 * umgekehrt.
 */
export const HINWEIS_TAGE = 365;

export type CookieEintrag = {
  name: string;
  zweck: string;
  dauer: string;
  quelle: string;
};

/** Was dieser Seite wirklich in den Browser gelegt wird. */
export const COOKIES: CookieEintrag[] = [
  {
    name: "next-auth.session-token",
    zweck: "Hält dich angemeldet. Ohne dieses Cookie gibt es kein Dashboard.",
    dauer: "30 Tage",
    quelle: "Anmeldung über Discord",
  },
  {
    name: "next-auth.csrf-token",
    zweck:
      "Verhindert, dass eine fremde Seite in deinem Namen Formulare abschickt.",
    dauer: "Sitzung",
    quelle: "Anmeldung über Discord",
  },
  {
    name: "next-auth.callback-url",
    zweck: "Merkt sich, auf welche Seite es nach dem Login zurückgeht.",
    dauer: "Sitzung",
    quelle: "Anmeldung über Discord",
  },
  {
    name: "wartung_bypass",
    zweck:
      "Nur für das Team: schaltet die Seite während einer Wartung wieder frei.",
    dauer: "8 Stunden",
    quelle: "Wartungsmodus",
  },
  {
    name: HINWEIS_COOKIE,
    zweck:
      "Merkt sich, dass du diesen Hinweis gesehen hast — sonst käme er bei jedem Aufruf wieder.",
    dauer: "1 Jahr",
    quelle: "Dieser Hinweis",
  },
  {
    name: BESUCHER_COOKIE,
    zweck:
      "Eine Zufallszahl ohne Bezug zu deiner Person. Sie verbindet deine Bestätigung mit dem Nachweis, den wir dafür führen müssen.",
    dauer: "1 Jahr",
    quelle: "Dieser Hinweis",
  },
];

/**
 * Ein Cookie lesen.
 *
 * `document.cookie` ist eine einzige Zeichenkette; ohne das Trennen an
 * `; ` trifft ein `includes`-Vergleich auch ein Cookie, dessen Name
 * zufällig endet wie der gesuchte.
 */
export function leseCookie(name: string): string {
  if (typeof document === "undefined") return "";
  for (const teil of document.cookie.split(";")) {
    const [schluessel, ...rest] = teil.trim().split("=");
    if (schluessel === name) return decodeURIComponent(rest.join("="));
  }
  return "";
}

/**
 * Ein Cookie setzen.
 *
 * `SameSite=Lax` und nicht `None`: Diese Cookies haben in einem fremden
 * `<iframe>` nichts zu suchen. `Secure` nur über HTTPS — auf
 * `http://localhost` würde der Browser das Cookie sonst stillschweigend
 * verwerfen, und die Entwicklung liefe gegen ein Fenster, das sich
 * nicht schließen lässt.
 */
export function setzeCookie(name: string, wert: string, tage: number): void {
  if (typeof document === "undefined") return;
  const ablauf = new Date(Date.now() + tage * 86400 * 1000).toUTCString();
  const sicher = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie =
    `${name}=${encodeURIComponent(wert)}; expires=${ablauf}; path=/; SameSite=Lax${sicher}`;
}

/**
 * Eine Kennung für diesen Browser — erzeugt, nicht erhoben.
 *
 * Sie sagt „dieser Browser“, sonst nichts: keine IP, kein Fingerabdruck,
 * nichts, was auf eine Person zurückführt. Ohne sie ließe sich eine
 * Bestätigung keiner Zeile zuordnen, und der Nachweis wäre eine
 * Strichliste.
 *
 * `randomUUID` gibt es nur in einem sicheren Kontext (HTTPS oder
 * localhost). Über einfaches HTTP ist die Funktion schlicht nicht
 * vorhanden — ohne Rückfallweg bliebe das Fenster dort für immer
 * stehen, weil das Speichern jedes Mal scheitert.
 */
export function besucherId(): string {
  const vorhanden = leseCookie(BESUCHER_COOKIE);
  if (vorhanden) return vorhanden;

  const neu =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : ersatzId();

  setzeCookie(BESUCHER_COOKIE, neu, HINWEIS_TAGE);
  return neu;
}

/**
 * Dieselbe Form wie `randomUUID`, falls es die Funktion nicht gibt.
 *
 * Die Form ist wichtig: der Bot prüft die Kennung gegen genau dieses
 * Muster und weist alles andere ab. Ein Ersatz in anderer Form würde
 * heißen, dass über HTTP nichts gespeichert wird — und niemand sähe,
 * warum.
 */
function ersatzId(): string {
  const zeichen = "0123456789abcdef";
  const zufall = (n: number) =>
    Array.from({ length: n }, () =>
      zeichen[Math.floor(Math.random() * 16)]
    ).join("");
  return [zufall(8), zufall(4), zufall(4), zufall(4), zufall(12)].join("-");
}
