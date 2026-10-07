"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { Language, translations, TranslationKey } from "./translations";
import { translateDashboardDom } from "./dom-translations";
import { validLanguage } from "./browser-language";
import { notifyLocaleChange } from "./locale";

interface LanguageContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: (key: TranslationKey) => string;
}

const LanguageContext = createContext<LanguageContextType>({
  language: "de",
  setLanguage: () => {},
  t: (key: TranslationKey) => key,
});

export function LanguageProvider({ children, initialLanguage = "de" }: { children: ReactNode; initialLanguage?: Language }) {
  const [language, setLanguageState] = useState<Language>(initialLanguage);

  useEffect(() => {
    // Explicit links (including the signed OAuth result) take priority. The
    // cookie also lets server-rendered pages start in the selected language.
    const requested = validLanguage(new URLSearchParams(window.location.search).get("lang"));
    let saved: Language | null = null;
    try { saved = validLanguage(localStorage.getItem("language")); } catch {}
    const selected = requested || saved || initialLanguage;
    setLanguageState(selected);
    document.documentElement.lang = selected;
    notifyLocaleChange();
    document.cookie = `website-language=${selected}; Path=/; Max-Age=31536000; SameSite=Lax${location.protocol === "https:" ? "; Secure" : ""}`;
    try { localStorage.setItem("language", selected); } catch {}
  }, [initialLanguage]);

  useEffect(() => {
    let scheduled = false;
    let frame = 0;

    const applyTranslations = () => {
      scheduled = false;
      translateDashboardDom(language);
    };

    const scheduleTranslations = () => {
      if (scheduled) return;
      scheduled = true;
      frame = requestAnimationFrame(applyTranslations);
    };

    document.documentElement.lang = language;
    notifyLocaleChange();
    scheduleTranslations();

    // Translate content rendered after navigation, suspense/loading states, API
    // responses, or client component state updates.
    const observer = new MutationObserver((mutations) => {
      if (
        mutations.some(
          (mutation) =>
            mutation.type === "characterData" ||
            mutation.type === "attributes" ||
            Array.from(mutation.addedNodes).some(
              (node) => node.nodeType === Node.TEXT_NODE || node.nodeType === Node.ELEMENT_NODE,
            ),
        )
      ) {
        scheduleTranslations();
      }
    });

    observer.observe(document.body, {
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["placeholder", "title", "aria-label", "alt"],
      subtree: true,
    });

    return () => { observer.disconnect(); cancelAnimationFrame(frame); };
  }, [language]);

  const setLanguage = (lang: Language) => {
    setLanguageState(lang);
    const url = new URL(window.location.href);
    if (url.searchParams.has("lang")) {
      url.searchParams.set("lang", lang);
      window.history.replaceState(window.history.state, "", url);
    }
    try { localStorage.setItem("language", lang); } catch {}
    document.cookie = `website-language=${lang}; Path=/; Max-Age=31536000; SameSite=Lax${location.protocol === "https:" ? "; Secure" : ""}`;
    document.documentElement.lang = lang;
    notifyLocaleChange();
    translateDashboardDom(lang);
  };

  const t = (key: TranslationKey): string => {
    return translations[language][key] || translations.en[key] || key;
  };

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  return useContext(LanguageContext);
}
