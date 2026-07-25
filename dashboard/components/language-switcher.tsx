"use client";

import React, { useState, useRef, useEffect } from "react";
import { useLanguage } from "@/lib/i18n/LanguageContext";
import { Globe } from "lucide-react";

export function LanguageSwitcher() {
  const { language, setLanguage, t } = useLanguage();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

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

      {open && (
        <div className="absolute right-0 top-full mt-2 w-40 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl overflow-hidden z-50">
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
        </div>
      )}
    </div>
  );
}
