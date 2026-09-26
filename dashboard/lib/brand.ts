/**
 * Der Name des Bots — eine einzige Stelle im Frontend.
 *
 * ── Warum der Name nicht uebersetzt wird ────────────────────────────
 *
 * Ein Produktname ist keine Vokabel. „University Bot" heißt so in
 * Deutschland und in England; „Universitätsbot" ist eine Uebersetzung
 * davon und damit ein zweiter Name für dasselbe Ding. Zwei Namen
 * bedeuten: die Suche findet nur einen davon, Nutzer zitieren den Bot
 * falsch, und im Support sitzt jemand, der „Universitätsbot" sagt und
 * „University Bot" meint.
 *
 * ── Warum nicht einfach die Umgebungsvariable ───────────────────────
 *
 * Vorher las jede Seite `NEXT_PUBLIC_BRAND_NAME` mit der Vorgabe
 * „University Bot". Live stand in Railway aber „Universitätsbot" darin,
 * und damit war jede einzelne Seite zweisprachig benannt, obwohl der
 * Quelltext durchgehend richtig war — nachgemessen am 27.08.2026 im
 * Browser (Navigation, Überschrift, Seitentitel). Eine Variable, die den
 * Namen pro Deployment frei lässt, ist für einen Produktnamen die
 * falsche Freiheit.
 *
 * Deshalb: Die Vorgabe ist der Name. Eine gesetzte Variable wird nur
 * dann übernommen, wenn sie *eine Variante des Namens* ist — solche
 * Varianten werden auf den einen Namen zurückgeführt. Was wirklich ein
 * anderer Name sein soll, bleibt möglich; alles, was nur eine andere
 * Schreibweise desselben ist, nicht.
 *
 * Die Bot-Seite hält dieselbe Regel in `bot/utils/config.py`. Beide
 * Stellen absichtlich getrennt: das Dashboard läuft im Browser und darf
 * nicht vom Python-Modul abhaengen.
 */

/** Der eine Name. */
export const BRAND = "University Bot";

/** Eine Schreibweise in eine Vergleichsform bringen. */
function schluessel(wert: string): string {
  return (wert || "")
    .trim()
    .toLowerCase()
    .replace(/ä/g, "ae")
    .replace(/ö/g, "oe")
    .replace(/ü/g, "ue")
    .replace(/ß/g, "ss")
    .replace(/[-\s]/g, "");
}

/**
 * Schreibweisen, die nur Varianten des Namens sind.
 *
 * Die Menge wird ueber dieselbe Funktion gebaut wie der Suchschluessel.
 * Eine von Hand gepflegte Menge mit Umlauten wuerde nie getroffen —
 * die Eingabe ist vorher umgerechnet, der Eintrag nicht. Genau dieser
 * Fehler steckt in der Python-Fassung nicht, weil dort dasselbe Muster
 * verwendet wird; dieser Kommentar sichert die Regel fuer beide Seiten.
 */
const ROHVARIANTEN = [
  "UniversityBot",
  "Universitätsbot",
  "Universität-Bot",
  "University Bot",
  "Uni Bot",
  "UB",
  "Oskar Bot",
  "Oskar-Bot",
  "universitybot X",
];

const VARIANTEN = new Set(ROHVARIANTEN.map(schluessel));

/**
 * Eine Schreibweise des Namens auf den Namen zurueckfuehren.
 *
 * Leerzeichen, Bindestriche, Groessen und Umlaute sind nur Varianten
 * desselben Namens, keine eigene Marke.
 */
export function normalisiereMarke(wert: string | undefined | null): string {
  const roh = (wert || "").trim();
  if (!roh) return BRAND;
  return VARIANTEN.has(schluessel(roh)) ? BRAND : roh;
}

/**
 * Das Kürzel im Logo.
 *
 * Kein zweiter Name, sondern ein Wortzeichen — deshalb bleibt die
 * Umgebungsvariable hier erlaubt.
 */
export const BRAND_WORD =
  (process.env.NEXT_PUBLIC_BRAND_NAME_WORD || "UB").trim() || "UB";
