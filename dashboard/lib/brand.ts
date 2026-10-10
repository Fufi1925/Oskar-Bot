/**
 * Gemeinsamer Produktname im Frontend.
 * Alte Konfigurationswerte werden auf CloudTIX zurückgeführt.
 * Die Bot-Seite hält dieselbe Regel in bot/utils/config.py.
 */

/** Der eine Name. */
export const BRAND = "CloudTIX";

/** Version of the shared Cloudtix artwork; also refreshes cached favicons. */
export const BRAND_ASSET_VERSION = "26d55bf24aa4";

export function brandAsset(filename: string): string {
  return `/${encodeURIComponent(filename)}?v=${BRAND_ASSET_VERSION}`;
}

export const BRAND_LOGO = brandAsset("cloudtix_pf weiß.gif");

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
  "CloudTIX",
  "Universiteit Bot",
  "Universiteitsbot",
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

/** Wortzeichen; alte Kürzel werden ebenfalls auf CloudTIX zurückgeführt. */
export const BRAND_WORD = normalisiereMarke(process.env.NEXT_PUBLIC_BRAND_NAME_WORD);
