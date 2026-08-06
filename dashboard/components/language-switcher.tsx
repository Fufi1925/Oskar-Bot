"use client";

import React, { useState, useRef } from "react";
import { useLanguage } from "@/lib/i18n/LanguageContext";
import { Globe } from "lucide-react";
import { PopoverLayer } from "@/components/ui/popover-layer";

export function LanguageSwitcher() {
  const { language, setLanguage, t } = useLanguage();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Klick daneben und Escape uebernimmt `PopoverLayer`. Ein eigener
  // Haken waere hier sogar falsch: die Liste haengt per Portal an
  // `document.body` und liegt nicht mehr in `ref`, ein Klick auf eine
  // Sprache haette also als "daneben" gezaehlt.

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-800/50 border border-slate-700/50 text-slate-300 hover:bg-slate-700/50 hover:text-white transition-all text-sm font-medium"
        title={t("language")}
      >
        <Globe className="h-4 w-4" />
        <span className="uppercase text-xs font-bold tracking-wider">
          {language === "de" ? "DE" : "EN"}
        </span>
      </button>

      <PopoverLayer
        anchor={ref}
        open={open}
        onClose={() => setOpen(false)}
        align="end"
        width={160}
        minHeight={0}
        maxHeight={200}
        className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl"
      >
          <button
            onClick={() => { setLanguage("de"); setOpen(false); }}
            className={`w-full flex items-center gap-3 px-4 py-3 text-sm transition-colors ${
              language === "de" 
                ? "bg-blue-500/10 text-blue-400 border-l-2 border-blue-500" 
                : "text-slate-300 hover:bg-slate-800 hover:text-white"
            }`}
          >
            <span className="text-lg">🇩🇪</span>
            <span className="font-medium">{t("german")}</span>
          </button>
          <button
            onClick={() => { setLanguage("en"); setOpen(false); }}
            className={`w-full flex items-center gap-3 px-4 py-3 text-sm transition-colors ${
              language === "en" 
                ? "bg-blue-500/10 text-blue-400 border-l-2 border-blue-500" 
                : "text-slate-300 hover:bg-slate-800 hover:text-white"
            }`}
          >
            <span className="text-lg">🇬🇧</span>
            <span className="font-medium">{t("english")}</span>
          </button>
      </PopoverLayer>
    </div>
  );
}
