"use client";

import { BRAND_LOGO } from "@/lib/brand";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, Check, ShieldCheck, ShieldX, RefreshCw, LockKeyhole, ArrowUpRight, AlertTriangle } from "lucide-react";
import { useLanguage } from "@/lib/i18n/LanguageContext";
import type { Language } from "@/lib/i18n/translations";
import type { VerifyResult as Outcome } from "@/lib/verification-oauth";

export const verificationCopy = {
  de: {
    label: "Discord-Verifizierung", successTitle: "Du bist verifiziert!", deniedTitle: "Verifizierung abgelehnt", errorTitle: "Verifizierung nicht abgeschlossen",
    successText: "Dein Konto wurde geprüft. Deine Serverrollen wurden erfolgreich vergeben.",
    deniedText: "Du erfüllst die Verifizierungsanforderungen dieses Servers nicht. Wende dich an das Serverteam, wenn du Hilfe benötigst.",
    errorText: "Die sichere Discord-Prüfung konnte nicht abgeschlossen werden. Starte sie erneut oder wende dich an das Serverteam.",
    invalid: "Dieser Ergebnislink ist ungültig oder abgelaufen. Starte die Verifizierung erneut über das Discord-Panel.",
    server: "Dein Server", roles: "Vergebene Rollen", blocked: "Eingeschränkte Server", next: "Deine nächsten Schritte",
    successNext: "Öffne deinen Server in Discord. Die freigeschalteten Kanäle hängen von deinen Rollen ab.",
    deniedNext: "Wende dich an das Serverteam, wenn du Hilfe mit den Anforderungen benötigst.",
    errorNext: "Du kannst die Prüfung erneut starten. Es werden dadurch keine zusätzlichen Rechte angefordert.",
    discord: "Zurück zu Discord", retry: "Erneut mit Discord prüfen", home: "Zur Website", privacy: "Datenschutz", secure: "Sicher mit Discord OAuth2",
    privacyText: "Es werden nur deine Discord-Identität und Servermitgliedschaften gelesen. Access-Tokens und Serverlisten werden nicht gespeichert. Bei ausdrücklich aktiviertem User Pull bleibt nur die verschlüsselte, widerrufbare Refresh-Autorisierung erhalten.",
    reasons: {
      not_configured: "Die Verifizierung ist auf diesem Server noch nicht vollständig eingerichtet.",
      role_unavailable: "University Bot kann die Verifiziert-Rolle aktuell nicht vergeben. Das Serverteam muss Rollen-Hierarchie und Bot-Berechtigungen prüfen.",
      oauth_token_failed: "Discord hat den Anmeldecode nicht akzeptiert. Starte die Prüfung bitte erneut.",
      oauth_identity_failed: "Discord konnte Identität oder Servermitgliedschaften vorübergehend nicht bereitstellen.",
      verification_failed: "Die Verbindung zur Verifizierung ist vorübergehend fehlgeschlagen. Starte die Prüfung bitte erneut.",
      oauth_cancelled: "Die Verifizierung wurde abgebrochen. Du kannst sie jederzeit erneut starten.",
      oauth_unavailable: "Die Discord-Verifizierung ist gerade nicht verfügbar. Bitte versuche es später erneut.",
    } as Record<string, string>,
  },
  en: {
    label: "Discord verification", successTitle: "You're verified!", deniedTitle: "Verification declined", errorTitle: "Verification incomplete",
    successText: "Your account was checked. Your server roles were assigned successfully.",
    deniedText: "You do not meet this server's verification requirements. Contact the server staff if you need help.",
    errorText: "The secure Discord check could not be completed. Try again or contact the server staff.",
    invalid: "This result link is invalid or has expired. Start verification again from the Discord panel.",
    server: "Your server", roles: "Assigned roles", blocked: "Restricted servers", next: "Your next steps",
    successNext: "Open your server in Discord. Your roles determine which channels you can access.",
    deniedNext: "Contact the server staff if you need help with the requirements.",
    errorNext: "You can restart the check. This does not request any additional permissions.",
    discord: "Return to Discord", retry: "Verify with Discord again", home: "Visit website", privacy: "Privacy", secure: "Secured with Discord OAuth2",
    privacyText: "Only your Discord identity and server memberships are read. Access tokens and server lists are not stored. If User Pull is explicitly enabled, only the encrypted, revocable refresh authorization is retained.",
    reasons: {
      not_configured: "Verification has not been fully configured on this server yet.",
      role_unavailable: "University Bot cannot assign the verified role right now. The server staff need to check the role hierarchy and bot permissions.",
      oauth_token_failed: "Discord did not accept the authorization code. Please start verification again.",
      oauth_identity_failed: "Discord temporarily could not provide your identity or server memberships.",
      verification_failed: "The verification connection temporarily failed. Please try again.",
      oauth_cancelled: "Verification was cancelled. You can start it again at any time.",
      oauth_unavailable: "Discord verification is currently unavailable. Please try again later.",
    } as Record<string, string>,
  },
};

export function VerifyResult({ guildId, language: initialLanguage, outcome }: { guildId: string; language: Language; outcome: Outcome | null }) {
  const { language, setLanguage } = useLanguage();
  const [selected, setSelected] = useState(initialLanguage);
  const initialized = useRef(false);
  useEffect(() => {
    if (initialized.current) setSelected(language);
    initialized.current = true;
  }, [language]);
  const c = verificationCopy[selected];
  const status = outcome?.status || "error";
  const success = status === "success";
  const denied = status === "denied";
  const Icon = success ? ShieldCheck : denied ? ShieldX : AlertTriangle;
  const color = success ? "text-emerald-300" : denied ? "text-rose-300" : "text-amber-300";
  const tint = success ? "bg-emerald-400/10 border-emerald-400/20" : denied ? "bg-rose-400/10 border-rose-400/20" : "bg-amber-400/10 border-amber-400/20";
  const title = success ? c.successTitle : denied ? c.deniedTitle : c.errorTitle;
  const text = !outcome ? c.invalid : success ? c.successText : denied ? c.deniedText : c.reasons[outcome.reason || ""] || c.errorText;
  const retryAvailable = status === "error" && /^\d{17,20}$/.test(guildId);
  return <main data-no-translate className="min-h-screen bg-[#18191c] px-4 py-8 text-white sm:py-14">
    <div className="mx-auto max-w-3xl">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <Link href="/" className="flex items-center gap-3"><img src={BRAND_LOGO} alt="University Bot" className="h-10 w-10 rounded-xl object-cover" /><span className="font-semibold">University Bot</span></Link>
        <div role="group" aria-label={selected === "en" ? "Language" : "Sprache"} className="flex rounded-xl border border-white/10 bg-[#202124] p-1">
          {(["de", "en"] as const).map(lang => <button type="button" key={lang} aria-pressed={selected === lang} onClick={() => { setSelected(lang); setLanguage(lang); }} className={`rounded-lg px-3 py-2 text-sm transition ${selected === lang ? "bg-white/10 text-white" : "text-slate-400 hover:text-white"}`}>{lang === "de" ? "Deutsch" : "English"}</button>)}
        </div>
      </header>
      <section className="overflow-hidden rounded-3xl border border-white/[.08] bg-[#202124] shadow-xl shadow-black/10">
        <div className="p-6 sm:p-10">
          <div className={`mb-6 grid h-16 w-16 place-items-center rounded-2xl border ${tint}`}><Icon className={`h-8 w-8 ${color}`} /></div>
          <p className={`mb-3 text-sm font-medium ${color}`}>{c.label}</p>
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h1>
          <p className="mt-4 max-w-xl text-base leading-7 text-slate-400">{text}</p>
          {outcome && <div className="mt-8 rounded-2xl border border-white/[.07] bg-[#18191c] p-4 sm:p-5">
            <div className="flex items-center gap-4">
              {outcome.guild_icon ? <img src={outcome.guild_icon} alt="" className="h-12 w-12 rounded-xl" /> : <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-blue-400/10 text-xl font-medium text-blue-300">{(outcome.guild_name || "D").slice(0, 1)}</span>}
              <div className="min-w-0"><p className="text-xs text-slate-500">{c.server}</p><p className="mt-1 break-words font-medium">{outcome.guild_name || "Discord"}</p></div>
              {success && <Check className="ml-auto h-5 w-5 shrink-0 text-emerald-300" />}
            </div>
            {success && outcome.role_name && <div className="mt-4 border-t border-white/[.07] pt-4 text-sm"><p className="text-slate-500">{c.roles}</p><p className="mt-1 break-words text-slate-200">{outcome.role_name}</p></div>}
            {!!outcome.blocked?.length && <div className="mt-4 border-t border-white/[.07] pt-4 text-sm"><p className="text-slate-500">{c.blocked}</p><p className="mt-1 break-words text-rose-300">{outcome.blocked.map(item => item.name).join(", ")}</p></div>}
          </div>}
          <div className="mt-7"><h2 className="text-sm font-medium text-white">{c.next}</h2><p className="mt-2 text-sm leading-6 text-slate-400">{success ? c.successNext : denied ? c.deniedNext : outcome ? c.errorNext : c.invalid}</p></div>
          <div className="mt-7 flex flex-col gap-3 sm:flex-row">
            {success && <a href={`https://discord.com/channels/${encodeURIComponent(guildId)}`} className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-[#5865f2] px-5 py-3 text-sm font-medium transition hover:bg-[#6772f5]">{c.discord}<ArrowUpRight className="h-4 w-4" /></a>}
            {retryAvailable && <a href={`/api/verify/start?guild=${encodeURIComponent(guildId)}&lang=${selected}`} className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-[#5865f2] px-5 py-3 text-sm font-medium transition hover:bg-[#6772f5]"><RefreshCw className="h-4 w-4" />{c.retry}</a>}
            <Link href="/" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-white/10 px-5 py-3 text-sm font-medium text-slate-300 transition hover:bg-white/5">{c.home}<ArrowRight className="h-4 w-4" /></Link>
          </div>
        </div>
        <footer className="border-t border-white/[.07] bg-[#18191c]/50 p-6 sm:px-10">
          <p className="flex items-center gap-2 text-sm text-slate-300"><LockKeyhole className="h-4 w-4 text-blue-300" />{c.secure}</p>
          <p className="mt-3 text-xs leading-6 text-slate-500">{c.privacyText}</p>
          <Link href="/privacy" className="mt-3 inline-block text-xs text-blue-300 hover:underline">{c.privacy}</Link>
        </footer>
      </section>
    </div>
  </main>;
}
