"use client";

/**
 * Die Karten der Teammitglieder.
 *
 * ── Warum eine Client-Komponente ────────────────────────────────────
 *
 * Wegen genau einer Sache: dem Kopieren der Discord-ID. Vorher stand
 * die ID als toter Text auf der Karte — achtzehn Ziffern, die man
 * abschreiben durfte, wenn man jemanden im Discord suchen wollte. Eine
 * Zahl hinzuschreiben, die niemand fehlerfrei abtippt, ist keine
 * Kontaktmöglichkeit.
 *
 * Alles andere kommt fertig vom Server: Namen und Avatare holt die
 * Seite selbst, bevor sie ausgeliefert wird. Sie stehen sofort da und
 * nicht erst nach einem Nachladen.
 *
 * ── Warum Initialen statt eines Platzhalterbildes ───────────────────
 *
 * Ein Avatar-Link lässt sich aus einer ID nicht bauen — der CDN-Pfad
 * braucht den Avatar-Hash, den nur der Bot kennt. Läuft der gerade
 * nicht, gibt es kein Bild. Ein graues Kästchen sähe dann nach Fehler
 * aus; die Initialen sehen nach Absicht aus.
 */

import React from "react";
import { Check, Copy, MessageCircle } from "lucide-react";

export interface Mitglied {
  id: string;
  name: string;
  role: string;
  description?: string;
  website?: string;
  /** Kommt vom Server: der echte Discord-Name, falls erreichbar. */
  liveName?: string | null;
  /** Kommt vom Server: die fertige Avatar-Adresse, falls erreichbar. */
  avatar?: string | null;
}

/** Die ersten Buchstaben, wenn kein Bild da ist. */
function initialen(name: string) {
  return name
    .split(/[\s_-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((teil) => teil[0]?.toUpperCase())
    .join("");
}

export function TeamMitglieder({ mitglieder }: { mitglieder: Mitglied[] }) {
  // Welche ID gerade kopiert wurde — für die kurze Rückmeldung am
  // Knopf. Eine ID ohne Rückmeldung lässt einen im Unklaren, ob der
  // Klick angekommen ist, und man klickt ein zweites Mal.
  const [kopiert, setKopiert] = React.useState("");

  // Der Merker muss zurückgesetzt werden, sonst bleibt das Häkchen für
  // immer stehen. Der Zeitgeber hängt am Wert, nicht am Klick: sonst
  // sammeln sich bei schnellem Klicken mehrere an, und der erste
  // löscht die Rückmeldung des zweiten.
  React.useEffect(() => {
    if (!kopiert) return;
    const zeit = setTimeout(() => setKopiert(""), 1800);
    return () => clearTimeout(zeit);
  }, [kopiert]);

  const kopieren = async (id: string) => {
    try {
      await navigator.clipboard.writeText(id);
      setKopiert(id);
    } catch {
      // Ohne HTTPS gibt es die Zwischenablage nicht. Dann bleibt die
      // ID wenigstens markierbar -- deshalb steht sie weiter als Text
      // da und nicht nur im Knopf.
    }
  };

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {mitglieder.map((person) => {
        const name = person.liveName || person.name;
        const istKopiert = kopiert === person.id;

        return (
          <article
            key={person.id || person.name}
            className="group rounded-2xl border border-slate-800 bg-[#131318] p-6 transition-colors hover:border-slate-700"
          >
            <div className="flex items-start gap-4">
              {person.avatar ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={person.avatar}
                  alt={`Profilbild von ${name}`}
                  width={56}
                  height={56}
                  className="h-14 w-14 shrink-0 rounded-2xl border border-slate-800 object-cover"
                />
              ) : (
                <div className="grid h-14 w-14 shrink-0 place-items-center rounded-2xl border border-indigo-500/25 bg-indigo-500/10 text-lg font-black text-indigo-300">
                  {initialen(name)}
                </div>
              )}
              <div className="min-w-0">
                <h3 className="truncate text-[17px] font-bold text-white">
                  {name}
                </h3>
                <p className="mt-1 text-[13px] font-semibold text-indigo-400">
                  {person.role}
                </p>
              </div>
            </div>

            {person.description && (
              <p className="mt-4 text-[14px] leading-relaxed text-slate-400">
                {person.description}
              </p>
            )}

            <div className="mt-5 flex items-center gap-2 border-t border-slate-800 pt-4">
              <MessageCircle
                className="h-4 w-4 shrink-0 text-slate-600"
                aria-hidden="true"
              />
              <code className="truncate font-mono text-[12px] text-slate-500">
                {person.id}
              </code>
              <button
                type="button"
                onClick={() => kopieren(person.id)}
                // Der Text ändert sich mit, nicht nur das Symbol: wer
                // einen Screenreader benutzt, sieht kein Häkchen.
                aria-label={
                  istKopiert
                    ? `Discord-ID von ${name} kopiert`
                    : `Discord-ID von ${name} kopieren`
                }
                className="ml-auto flex shrink-0 items-center gap-1.5 rounded-lg border border-slate-800 bg-[#0e0e12] px-2.5 py-1.5 text-[12px] font-semibold text-slate-400 transition-colors hover:border-slate-700 hover:text-white"
              >
                {istKopiert ? (
                  <>
                    <Check className="h-3.5 w-3.5 text-emerald-400" />
                    Kopiert
                  </>
                ) : (
                  <>
                    <Copy className="h-3.5 w-3.5" />
                    ID
                  </>
                )}
              </button>
            </div>
          </article>
        );
      })}
    </div>
  );
}
