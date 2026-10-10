"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowLeft, RefreshCw } from "lucide-react";
import { useLanguage } from "@/lib/i18n/LanguageContext";

export default function DashboardError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const { language } = useLanguage();
  const t = (de: string, en: string) => language === "en" ? en : de;
  useEffect(() => { console.error("Dashboard Error:", error); }, [error]);
  return <div className="grid min-h-[65vh] place-items-center" data-no-translate><section role="alert" className="w-full max-w-lg rounded-2xl border border-white/10 bg-[#111111] p-7 text-center sm:p-10"><span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl border border-white/15 bg-white/[.035] text-slate-300"><AlertTriangle size={25} /></span><p className="mt-6 text-[9px] tracking-[.13em] text-slate-500">CLOUDTIX WORKSPACE</p><h1 className="mt-3 text-2xl font-semibold text-white">{t("Die Seite konnte nicht geladen werden.", "This page could not be loaded.")}</h1><p className="mt-4 text-sm leading-relaxed text-slate-400">{t("Versuche es erneut oder gehe zu deiner Übersicht zurück.", "Try again or return to your dashboard overview.")}</p><div className="mt-7 flex flex-col justify-center gap-3 sm:flex-row"><button type="button" onClick={reset} className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-4 py-3 text-xs font-semibold text-black"><RefreshCw size={14} />{t("Erneut laden", "Try again")}</button><Link href="/dashboard" className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/15 px-4 py-3 text-xs text-slate-300"><ArrowLeft size={14} />{t("Zur Übersicht", "Back to overview")}</Link></div>{process.env.NODE_ENV === "development" && <pre className="mt-6 overflow-auto rounded-xl bg-black/40 p-4 text-left text-xs text-slate-400">{error.message}</pre>}</section></div>;
}
