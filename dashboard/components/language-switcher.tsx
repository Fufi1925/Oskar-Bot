"use client";

import React, { useState, useRef } from "react";
import { useLanguage } from "@/lib/i18n/LanguageContext";
import { ChevronDown } from "lucide-react";
import { PopoverLayer } from "@/components/ui/popover-layer";

/**
 * Der Sprachumschalter.
 *
 * Die Flagge steht VOR dem Namen — im Knopf wie in der Liste. Der
 * Knopf nennt die aktuelle Sprache mit Namen („🇩🇪 Deutsch“); auf
 * schmalen Bildschirmen fällt der Name weg und nur die Flagge bleibt,
 * weil in der Kopfzeile des Dashboards neben Glocke und Profil wenig
 * Platz ist.
 *
 * Klick daneben und Escape uebernimmt `PopoverLayer`. Ein eigener
 * Haken waere hier sogar falsch: die Liste haengt per Portal an
 * `document.body` und liegt nicht mehr in `ref`, ein Klick auf eine
 * Sprache haette also als "daneben" gezaehlt.
 */

// Flagge und Name je Sprache an einer Stelle — die beiden gehoeren
// zusammen und stehen deshalb nicht einzeln in Knopf und Liste.
const SPRACHEN = [
  { code: "de", flagge: "🇩🇪", name: "Deutsch" },
  { code: "en", flagge: "🇬🇧", name: "English" },
] as const;

export function LanguageSwitcher() {
  const { language, setLanguage, t } = useLanguage();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const aktuell = SPRACHEN.find((s) => s.code === language) ?? SPRACHEN[0];

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-800/50 border border-slate-700/50 text-slate-300 hover:bg-slate-700/50 hover:text-white transition-all text-sm font-medium"
        title={t("language")}
        aria-label={t("language")}
      >
        {/* Flagge zuerst — sie sagt die Sprache auch ohne Text. */}
        <span className="text-base leading-none">{aktuell.flagge}</span>
        <span className="hidden sm:inline text-xs font-bold tracking-wider">
          {aktuell.name}
        </span>
        <ChevronDown
          className={`h-3.5 w-3.5 text-slate-500 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      <PopoverLayer
        anchor={ref}
        open={open}
        onClose={() => setOpen(false)}
        align="end"
        width={190}
        minHeight={0}
        maxHeight={200}
        className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl"
      >
        {SPRACHEN.map((sprache) => (
          <button
            key={sprache.code}
            onClick={() => { setLanguage(sprache.code); setOpen(false); }}
            className={`w-full flex items-center gap-3 px-4 py-3 text-sm transition-colors ${
              language === sprache.code
                ? "bg-blue-500/10 text-blue-400 border-l-2 border-blue-500"
                : "text-slate-300 hover:bg-slate-800 hover:text-white"
            }`}
          >
            {/* Flagge vor dem Namen — in der Liste wie im Knopf. */}
            <span className="text-lg">{sprache.flagge}</span>
            <span className="font-medium">{sprache.name}</span>
            {language === sprache.code && (
              <span className="ml-auto text-blue-400">✓</span>
            )}
          </button>
        ))}
      </PopoverLayer>
    </div>
  );
}
