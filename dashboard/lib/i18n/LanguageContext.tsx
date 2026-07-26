"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { Language, translations, TranslationKey } from "./translations";
import { translateDashboardDom } from "./dom-translations";

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

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>("de");

  useEffect(() => {
    const saved = localStorage.getItem("language") as Language;
    if (saved && (saved === "de" || saved === "en")) {
      setLanguageState(saved);
      document.documentElement.lang = saved;
    } else {
      document.documentElement.lang = "de";
    }
  }, []);

  useEffect(() => {
    let scheduled = false;

    const applyTranslations = () => {
      scheduled = false;
      translateDashboardDom(language);
    };

    const scheduleTranslations = () => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(applyTranslations);
    };

    document.documentElement.lang = language;
    scheduleTranslations();

    // Translate content rendered after navigation, suspense/loading states, API
    // responses, or client component state updates.
    const observer = new MutationObserver((mutations) => {
      if (
        mutations.some((mutation) =>
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
      subtree: true,
    });

    return () => observer.disconnect();
  }, [language]);

  const setLanguage = (lang: Language) => {
    setLanguageState(lang);
    localStorage.setItem("language", lang);
    document.documentElement.lang = lang;
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
