"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, CheckCircle2, Clock3, Fingerprint, Globe2, KeyRound, Loader2, LockKeyhole, Search, ShieldCheck, Users, X } from "lucide-react";
import Link from "next/link";
import Image from "next/image";
import { useWebsiteLocale } from "@/lib/i18n/locale";
import { OwnerOAuthDetails, type OwnerOAuthSnapshot } from "./owner-oauth-details";

type Guild = { guild_id: string; guild_name: string; member_count: number; is_owner: boolean; is_admin: boolean; top_role: string | null; joined_at: number; roles: string[] };
type Result = {
  profile: { user_id: string; found: boolean; username: string | null; display_name: string | null; avatar: string | null; is_bot: boolean; created_at: number };
  bot: { guilds: Guild[]; members_intent: boolean; cached_member_data: boolean; ban: { reason: string; banned_at: number; banned_by: string } | null };
  dashboard: { first_seen: number; last_seen: number; login_count: number } | null;
  oauth: OwnerOAuthSnapshot | null;
};
const card = "rounded-2xl border border-white/[0.07] cloudtix-admin-card bg-[#11151e] p-5 sm:p-6";

export function OwnerLouckupPanel() {
  const locale = useWebsiteLocale();
  const t = useCallback((de: string, en: string) => locale === "en-GB" ? en : de, [locale]);
  const [ready, setReady] = useState(false), [configured, setConfigured] = useState(false);
  const [expires, setExpires] = useState(0), [now, setNow] = useState(Date.now());
  const [code, setCode] = useState(""), [id, setId] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [result, setResult] = useState<Result | null>(null), [filter, setFilter] = useState("");
  const controller = useRef<AbortController | null>(null);
  const unlocked = expires > now / 1000;
  const date = (value: number) => value ? new Date(value * 1000).toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" }) : "—";

  const errorText = (reason: string) => ({
    invalid_code: t("Der Code ist falsch, abgelaufen oder wurde bereits verwendet. Bitte nutze einen neuen Code.", "The code is incorrect, expired or already used. Please use a new code."),
    rate_limited: t("Zu viele Fehlversuche. Bitte warte fünf Minuten.", "Too many failed attempts. Please wait five minutes."),
    not_configured: t("Die Authenticator-Sperre muss zuerst in den Servereinstellungen eingerichtet werden.", "The authenticator gate needs to be configured in the server settings first."),
    sign_in_again: t("Bitte melde dich erneut mit Discord an.", "Please sign in with Discord again."),
    not_signed_in: t("Deine Anmeldung ist abgelaufen. Bitte melde dich erneut mit Discord an.", "Your session has expired. Please sign in with Discord again."),
    invalid_origin: t("Die Website-Adresse stimmt nicht mit der konfigurierten Dashboard-Adresse überein. Öffne das Dashboard über die in NEXTAUTH_URL eingestellte Adresse.", "The website address does not match the configured dashboard address. Open the dashboard at the address configured in NEXTAUTH_URL."),
    service_unavailable: t("Der Bot-Dienst ist momentan nicht erreichbar. Bitte versuche es gleich erneut.", "The bot service is currently unavailable. Please try again shortly."),
    owner_required: t("Dieser Bereich ist ausschließlich für feste Owner-IDs freigegeben.", "This area is restricted to configured owner IDs."),
  }[reason] || t("Die Anfrage konnte nicht abgeschlossen werden. Bitte versuche es erneut.", "The request could not be completed. Please try again."));

  useEffect(() => {
    const request = new AbortController();
    fetch("/api/owner-louckup/status", { cache: "no-store", signal: request.signal })
      .then(async response => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "request_failed");
        setConfigured(data.configured); setExpires(data.unlocked ? data.expires_at : 0);
      }).catch(error => { if (error.name !== "AbortError") setError(error.message); })
      .finally(() => { if (!request.signal.aborted) setReady(true); });
    return () => { request.abort(); controller.current?.abort(); };
  }, []);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  useEffect(() => { if (!unlocked) { controller.current?.abort(); setResult(null); setBusy(false); } }, [unlocked]);

  async function unlock(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const response = await fetch("/api/owner-louckup/unlock", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "request_failed");
      setNow(Date.now()); setExpires(data.expires_at); setCode("");
    } catch (error) { setError(error instanceof Error ? error.message : "request_failed"); }
    finally { setBusy(false); }
  }
  async function lock() {
    controller.current?.abort(); setExpires(0); setResult(null); setBusy(false); setCode(""); setError("");
    try { await fetch("/api/owner-louckup/lock", { method: "POST" }); } catch { /* The server also enforces expiry. */ }
  }
  async function search(event: React.FormEvent) {
    event.preventDefault(); setError(""); setResult(null); setBusy(true); setFilter("");
    controller.current?.abort(); const request = new AbortController(); controller.current = request;
    try {
      const response = await fetch(`/api/owner-louckup/users/${id.trim()}`, { cache: "no-store", signal: request.signal });
      const data = await response.json();
      if (response.status === 403 || response.status === 401) { setExpires(0); throw new Error(data.detail || "request_failed"); }
      if (!response.ok) throw new Error(data.detail || "request_failed");
      if (!request.signal.aborted) setResult(data);
    } catch (error) { if (error instanceof Error && error.name !== "AbortError") setError(error.message); }
    finally { if (!request.signal.aborted) setBusy(false); }
  }
  const field = (label: string, value: React.ReactNode) => <div className="min-w-0"><dt className="text-xs text-slate-500">{label}</dt><dd className="mt-1 break-words text-sm font-medium text-slate-200">{value ?? "—"}</dd></div>;
  const chip = (label: string) => <span className="rounded-md bg-blue-500/10 px-2 py-1 text-[11px] text-blue-300">{label}</span>;
  const matches = (name: string, guildId: string) => `${name} ${guildId}`.toLocaleLowerCase().includes(filter.trim().toLocaleLowerCase());

  return <section className="space-y-6 text-slate-200">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex items-center gap-4"><div className="rounded-2xl border border-blue-400/15 bg-blue-500/10 p-3 text-blue-400"><Fingerprint className="h-6 w-6" /></div><div><p className="text-xs font-medium uppercase tracking-[0.2em] text-slate-500">{t("Owner-Bereich", "Owner area")}</p><h1 className="mt-1 text-2xl font-semibold tracking-tight">Louckup</h1></div></div>
      <div className="flex items-center gap-3"><Link href="/dashboard/admin" className="flex items-center gap-2 text-xs text-slate-400 hover:text-white"><ArrowLeft className="h-3.5 w-3.5" />{t("Admin-Dashboard", "Admin dashboard")}</Link>{unlocked && <button onClick={lock} className="flex items-center gap-2 rounded-xl border border-white/10 px-3 py-2 text-xs hover:bg-white/5"><LockKeyhole className="h-3.5 w-3.5" />{t("Sperren", "Lock")}</button>}</div>
    </div>
    {!ready ? <div className={`${card} flex items-center justify-center gap-3 py-20 text-slate-400`}><Loader2 className="h-5 w-5 animate-spin" />{t("Zugriff wird geprüft…", "Checking access…")}</div> : !unlocked ?
      <div className="mx-auto max-w-lg rounded-3xl border border-white/[0.08] cloudtix-admin-card bg-[#11151e] p-7 sm:p-10">
        <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-500/10 text-blue-400"><LockKeyhole className="h-7 w-7" /></div>
        <h2 className="text-xl font-semibold">{t("Mit Authenticator bestätigen", "Confirm with your authenticator")}</h2>
        <p className="mt-3 text-sm leading-relaxed text-slate-400">{t("Gib den sechsstelligen Code deiner Authenticator-App ein, um Louckup zu öffnen. Der Code wechselt alle 30 Sekunden.", "Enter the six-digit code from your authenticator app to open Louckup. The code changes every 30 seconds.")}</p>
        {!configured && <p className="mt-4 rounded-xl border border-amber-400/15 bg-amber-500/5 p-3 text-sm text-amber-200">{errorText("not_configured")}</p>}
        <form onSubmit={unlock} className="mt-7 space-y-4"><label htmlFor="louckup-code" className="block text-xs font-medium text-slate-400">{t("Authenticator-Code", "Authenticator code")}</label><input id="louckup-code" value={code} onChange={event => setCode(event.target.value.replace(/[^0-9]/g, "").slice(0, 6))} type="text" inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="000000" disabled={!configured || busy} className="w-full rounded-xl border border-white/10 bg-black/20 px-4 py-4 text-center font-mono text-2xl tracking-[0.4em] outline-none focus:border-blue-400/60 disabled:opacity-40" /><button disabled={!configured || busy || code.length !== 6} className="flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 py-3 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-40">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}{t("Louckup entsperren", "Unlock Louckup")}</button></form>
        <p className="mt-5 flex items-center gap-2 text-xs text-slate-500"><ShieldCheck className="h-4 w-4" />{t("Nur feste Owner-IDs · Zugang für 10 Minuten", "Configured owner IDs only · 10-minute access")}</p>
      </div> : <>
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-400/10 bg-emerald-500/5 px-4 py-3 text-xs text-emerald-300"><span className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4" />{t("Owner-Zugriff und 2FA bestätigt", "Owner access and 2FA confirmed")}</span><span className="flex items-center gap-2"><Clock3 className="h-3.5 w-3.5" />{t("Verbleibend", "Remaining")}: {Math.floor(Math.max(0, expires - now / 1000) / 60)}:{String(Math.floor(Math.max(0, expires - now / 1000) % 60)).padStart(2, "0")}</span></div>
      <form onSubmit={search} className={card}><label htmlFor="louckup-id" className="text-sm font-medium">{t("Discord-Nutzer nachschlagen", "Look up a Discord user")}</label><p className="mt-1 text-xs text-slate-500">{t("Profil, gemeinsame Bot-Server und freigegebene OAuth-Daten an einem Ort.", "Profile, shared bot servers and authorized OAuth data in one place.")}</p><div className="mt-4 flex flex-col gap-3 sm:flex-row"><input id="louckup-id" inputMode="numeric" value={id} onChange={event => setId(event.target.value.replace(/[^0-9]/g, "").slice(0, 20))} placeholder={t("Discord-ID eingeben", "Enter a Discord ID")} className="min-w-0 flex-1 rounded-xl border border-white/10 bg-black/20 px-4 py-3 font-mono text-sm outline-none focus:border-blue-400/60" /><button disabled={busy || !/^[0-9]{17,20}$/.test(id)} className="flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 py-3 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-40">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}{t("Suchen", "Search")}</button></div></form>
      {result && <>
        <div className={card}><div className="flex items-center gap-4">{result.profile.avatar && result.profile.avatar.startsWith("https://cdn.discordapp.com/") ? <Image src={result.profile.avatar} alt="" width={56} height={56} unoptimized className="h-14 w-14 rounded-2xl" /> : <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white/5"><Users className="h-6 w-6 text-slate-500" /></div>}<div><h2 className="text-xl font-semibold">{result.profile.display_name || result.profile.username || result.profile.user_id}</h2><p className="mt-1 text-xs text-slate-500">{result.profile.found ? t("Discord-Profil", "Discord profile") : t("Kein abrufbares Discord-Profil gefunden", "No accessible Discord profile found")}</p></div></div><dl className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">{field(t("Discord-ID", "Discord ID"), result.profile.user_id)}{field(t("Benutzername", "Username"), result.profile.username)}{field(t("Konto erstellt", "Account created"), date(result.profile.created_at))}{field(t("Kontotyp", "Account type"), result.profile.found ? (result.profile.is_bot ? t("Bot", "Bot") : t("Nutzer", "User")) : "—")}</dl></div>
        <div className="grid gap-4 sm:grid-cols-3">{[[t("Gemeinsame Bot-Server", "Shared bot servers"), result.bot.guilds.length], [t("OAuth-Server", "OAuth servers"), result.oauth ? result.oauth.guilds.length : "—"], [t("Dashboard-Anmeldungen", "Dashboard sign-ins"), result.dashboard?.login_count ?? "—"]].map(([label, value]) => <div key={label} className={card}><p className="text-xs text-slate-500">{label}</p><p className="mt-3 text-3xl font-semibold tracking-tight">{typeof value === "number" ? value.toLocaleString(locale) : value}</p></div>)}</div>
        <div className="grid gap-4 lg:grid-cols-2"><div className={card}><h3 className="text-sm font-semibold">{t("Bot & Dashboard", "Bot & dashboard")}</h3><dl className="mt-5 grid grid-cols-2 gap-5">{field(t("Bot-Sperre", "Bot ban"), result.bot.ban ? t("Gesperrt", "Banned") : t("Keine Sperre", "No ban"))}{field(t("Zuletzt im Dashboard", "Last dashboard sign-in"), date(result.dashboard?.last_seen || 0))}{result.bot.ban && field(t("Sperrgrund", "Ban reason"), result.bot.ban.reason || "—")}{result.dashboard && field(t("Erste Dashboard-Anmeldung", "First dashboard sign-in"), date(result.dashboard.first_seen))}</dl></div><div className={card}><h3 className="text-sm font-semibold">{t("OAuth-Freigabe", "OAuth authorization")}</h3>{result.oauth ? <><dl className="mt-5 grid grid-cols-2 gap-5">{field(t("Quelle", "Source"), result.oauth.source === "verification" ? t("Server-Verifizierung", "Server verification") : t("Dashboard-Anmeldung", "Dashboard sign-in"))}{field(t("Stand der Daten", "Snapshot captured"), date(result.oauth.captured_at))}{field(t("Löschung spätestens", "Expires by"), date(result.oauth.expires_at))}{field(t("Serverliste", "Guild list"), result.oauth.complete ? t("Vollständig abgerufen", "Fully retrieved") : t("Teilweise abgerufen", "Partially retrieved"))}</dl><p className="mt-4 text-xs leading-relaxed text-slate-500">{t("Zeitpunkt der letzten Freigabe. Mitgliedschaften können sich inzwischen geändert haben.", "Recorded at the last authorization. Memberships may have changed since then.")}</p><div className="mt-4 flex flex-wrap gap-2">{result.oauth.scopes.map(scope => <span key={scope}>{chip(scope)}</span>)}</div></> : <p className="mt-4 text-sm leading-relaxed text-slate-500">{t("Keine aktuelle OAuth-Serverliste vorhanden. Daten erscheinen nach einer neuen Dashboard-Anmeldung oder Server-Verifizierung mit den bereits freigegebenen Berechtigungen.", "No current OAuth guild list is available. Data appears after a new dashboard sign-in or server verification using the already granted scopes.")}</p>}</div></div>
        {result.oauth && <div className={card}><h3 className="text-sm font-semibold">{t("Profil bei der OAuth-Freigabe", "Profile at OAuth authorization")}</h3><dl className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">{field(t("Benutzername", "Username"), result.oauth.profile.username as string)}{field(t("Anzeigename", "Display name"), result.oauth.profile.global_name as string)}{field(t("Öffentliche Profil-Flags", "Public profile flags"), result.oauth.profile.public_flags as number)}{field(t("Profilfarbe", "Profile color"), typeof result.oauth.profile.accent_color === "number" ? `#${result.oauth.profile.accent_color.toString(16).padStart(6, "0")}` : "—")}</dl>{typeof result.oauth.profile.banner === "string" && /^[a-zA-Z0-9_]{1,128}$/.test(result.oauth.profile.banner) && <Image width={1024} height={256} unoptimized src={`https://cdn.discordapp.com/banners/${result.profile.user_id}/${result.oauth.profile.banner}.${result.oauth.profile.banner.startsWith("a_") ? "gif" : "png"}?size=1024`} alt={t("Öffentliches Discord-Profilbanner", "Public Discord profile banner")} className="mt-5 max-h-48 w-full rounded-xl object-cover" />}</div>}
        <div className="relative"><Search className="absolute left-4 top-3.5 h-4 w-4 text-slate-500" /><input aria-label={t("Serverlisten filtern", "Filter server lists")} value={filter} onChange={event => setFilter(event.target.value)} placeholder={t("Server nach Name oder ID filtern", "Filter servers by name or ID")} className="w-full rounded-xl border border-white/10 cloudtix-admin-card bg-[#11151e] py-3 pl-11 pr-12 text-sm outline-none focus:border-blue-400/60" />{filter && <button onClick={() => setFilter("")} aria-label={t("Filter löschen", "Clear filter")} className="absolute right-4 top-3.5 text-slate-500"><X className="h-4 w-4" /></button>}</div>
        <div className={card}><h3 className="flex items-center gap-2 text-sm font-semibold"><Users className="h-4 w-4 text-blue-400" />{t("Gemeinsame Server mit dem Bot", "Servers shared with the bot")}</h3><p className="mt-2 text-xs text-slate-500">{t("Aus dem Mitglieder-Cache des Bots. Nicht eingelesene Mitglieder fehlen möglicherweise.", "From the bot's member cache. Members not loaded into the cache may be missing.")}</p>{!result.bot.members_intent && <p className="mt-2 text-xs text-amber-300">{t("Der Mitglieder-Intent ist deaktiviert; diese Liste ist möglicherweise unvollständig.", "The members intent is disabled; this list may be incomplete.")}</p>}<div className="mt-4 divide-y divide-white/5">{result.bot.guilds.filter(g => matches(g.guild_name, g.guild_id)).map(guild => <div key={guild.guild_id} className="py-4 first:pt-0"><div className="flex flex-wrap items-start justify-between gap-2"><div><p className="text-sm font-medium">{guild.guild_name}</p><p className="mt-1 font-mono text-[11px] text-slate-500">{guild.guild_id}</p></div><div className="flex gap-2">{guild.is_owner && chip(t("Inhaber", "Owner"))}{guild.is_admin && chip(t("Administrator", "Administrator"))}</div></div><dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">{field(t("Mitglieder", "Members"), guild.member_count.toLocaleString(locale))}{field(t("Beigetreten", "Joined"), date(guild.joined_at))}{field(t("Höchste Rolle", "Highest role"), guild.top_role)}</dl><div className="mt-3 flex flex-wrap gap-1.5">{guild.roles.map((role, i) => <span key={`${role}-${i}`} className="rounded-md bg-white/5 px-2 py-1 text-[11px] text-slate-400">{role}</span>)}</div></div>)}{!result.bot.guilds.filter(g => matches(g.guild_name, g.guild_id)).length && <p className="py-5 text-sm text-slate-500">{t("Keine passenden gemeinsamen Server gefunden.", "No matching shared servers found.")}</p>}</div></div>
        {result.oauth && <div className={card}><h3 className="flex items-center gap-2 text-sm font-semibold"><Globe2 className="h-4 w-4 text-blue-400" />{t("Durch OAuth freigegebene Server", "Guilds authorized through OAuth")}</h3><p className="mt-2 text-xs text-slate-500">{t("Enthält auch Server, auf denen der Bot nicht installiert ist.", "Includes servers where the bot is not installed.")}</p><div className="mt-4 divide-y divide-white/5">{result.oauth.guilds.filter(g => matches(g.name, g.id)).map(guild => {
          let admin = false, manage = false; try { const bits = BigInt(guild.permissions); admin = (bits & BigInt(8)) !== BigInt(0); manage = (bits & BigInt(32)) !== BigInt(0); } catch { /* Unknown permissions stay unknown. */ }
          return <div key={guild.id} className="flex flex-wrap items-center justify-between gap-3 py-4 first:pt-0"><div><p className="text-sm font-medium">{guild.name}</p><p className="mt-1 font-mono text-[11px] text-slate-500">{guild.id}</p></div><div className="flex flex-wrap gap-2">{guild.owner && chip(t("Inhaber", "Owner"))}{admin && chip(t("Administrator", "Administrator"))}{!admin && manage && chip(t("Server verwalten", "Manage server"))}{result.bot.guilds.some(g => g.guild_id === guild.id) && chip(t("Bot vorhanden", "Bot present"))}</div></div>;
        })}{!result.oauth.guilds.filter(g => matches(g.name, g.id)).length && <p className="py-5 text-sm text-slate-500">{t("Keine passenden OAuth-Server gefunden.", "No matching OAuth guilds found.")}</p>}</div></div>}
        {result.oauth && <OwnerOAuthDetails snapshot={result.oauth} filter={filter} />}
      </>}
    </>}
    {error && <div role="alert" className="rounded-xl border border-rose-400/20 bg-rose-500/5 px-4 py-3 text-sm text-rose-300">{errorText(error)}</div>}
  </section>;
}
