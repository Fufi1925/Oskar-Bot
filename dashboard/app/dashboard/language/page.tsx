"use client";

import Link from "next/link";
import { Check, Globe2, ArrowUpRight } from "lucide-react";
import { useLanguage } from "@/lib/i18n/LanguageContext";

export default function LanguagePage() {
  const { language, setLanguage } = useLanguage();
  const english = language === "en";
  return <section className="mx-auto max-w-4xl space-y-6">
    <header className="rounded-2xl border border-white/[.07] bg-[#202124] p-6 sm:p-8">
      <Globe2 className="mb-5 h-8 w-8 text-blue-300" />
      <h1 className="text-2xl font-semibold text-white">{english ? "Website language" : "Website-Sprache"}</h1>
      <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">{english
        ? "Choose a language for the entire website. Your selection also applies to the dashboard and Discord verification."
        : "Wähle die Sprache für die gesamte Website. Deine Auswahl gilt auch für das Dashboard und die Discord-Verifizierung."}</p>
    </header>
    <div className="grid gap-4 sm:grid-cols-2">
      {([{ code: "de", name: "Deutsch", flag: "🇩🇪", description: "German" }, { code: "en", name: "English", flag: "🇬🇧", description: "Englisch" }] as const).map(item =>
        <button key={item.code} type="button" onClick={() => setLanguage(item.code)} aria-pressed={language === item.code}
          className={`flex items-center gap-4 rounded-2xl border p-6 text-left transition ${language === item.code ? "border-blue-400/40 bg-blue-400/10" : "border-white/[.07] bg-[#202124] hover:border-white/20"}`}>
          <span className="text-3xl">{item.flag}</span>
          <span className="flex-1" data-no-translate><span className="block text-lg font-medium text-white">{item.name}</span><span className="mt-1 block text-sm text-slate-400">{item.description}</span></span>
          {language === item.code && <Check aria-label={english ? "Selected" : "Ausgewählt"} className="h-5 w-5 text-blue-300" />}
        </button>)}
    </div>
    <div className="rounded-2xl border border-white/[.07] bg-[#202124] p-6">
      <p className="text-sm leading-6 text-slate-400">{english
        ? "The language is saved on this device. Custom server texts and Discord messages are not translated automatically."
        : "Die Sprache wird auf diesem Gerät gespeichert. Eigene Servertexte und Discord-Nachrichten werden nicht automatisch übersetzt."}</p>
      <Link href="/" className="mt-5 inline-flex items-center gap-2 text-sm font-medium text-blue-300">{english ? "View website" : "Website anzeigen"}<ArrowUpRight className="h-4 w-4" /></Link>
    </div>
  </section>;
}
