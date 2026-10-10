"use client";

import { useEffect, useState } from "react";
import { KeyRound, Loader2, LogOut, Settings2, ShieldCheck, Users, X } from "lucide-react";
import { signOut } from "next-auth/react";
import { toast } from "sonner";
import { Switch } from "@/components/ui/switch";
import { useWebsiteLocale } from "@/lib/i18n/locale";

type Settings = { scopes: string[]; required_scopes: string[]; optional_scopes: string[]; updated_at: number; updated_by: string; revoked_before_ms: number; last_logout_by: string };
const all = ["identify", "connections", "guilds", "guilds.members.read"];
const card = "rounded-2xl border border-white/[0.07] cloudtix-admin-card bg-[#11151e] p-5 sm:p-6";

export function DashboardSettingsPanel({ currentUserId }: { currentUserId: string }) {
  const locale = useWebsiteLocale();
  const t = (de: string, en: string) => locale === "en-GB" ? en : de;
  const [settings, setSettings] = useState<Settings | null>(null), [scopes, setScopes] = useState<string[]>([]);
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [userId, setUserId] = useState(""), [confirm, setConfirm] = useState<"all" | "user" | null>(null);
  const dirty = !!settings && JSON.stringify(scopes) !== JSON.stringify(settings.scopes);
  const errorText = (reason: string) => ({
    owner_required: t("Nur feste Owner-IDs dürfen diese Einstellungen verwalten.", "Only configured owner IDs may manage these settings."),
    not_signed_in: t("Deine Sitzung ist abgelaufen. Bitte melde dich erneut an.", "Your session has expired. Please sign in again."),
    invalid_user_id: t("Bitte gib eine gültige Discord-Nutzer-ID ein.", "Please enter a valid Discord user ID."),
    required_scopes: t("identify und guilds werden für die Anmeldung und Serverzugriffe benötigt.", "identify and guilds are required for sign-in and guild access."),
    invalid_scopes: t("Diese OAuth-Berechtigung wird nicht unterstützt.", "This OAuth permission is not supported."),
    invalid_origin: t("Bitte öffne das Dashboard über seine konfigurierte Website-Adresse.", "Please open the dashboard at its configured website address."),
  }[reason] || t("Die Einstellungen konnten nicht verarbeitet werden. Bitte versuche es erneut.", "The settings could not be processed. Please try again."));
  async function call(action: string, method = "GET", body?: unknown) {
    const response = await fetch(`/api/dashboard-settings/${action}`, {
      method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body), cache: "no-store",
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "request_failed");
    return data;
  }
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/dashboard-settings/settings", { cache: "no-store", signal: controller.signal })
      .then(async response => { const data = await response.json(); if (!response.ok) throw new Error(data.detail || "request_failed"); setSettings(data); setScopes(data.scopes); })
      .catch(error => { if (error.name !== "AbortError") setError(error.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!confirm) return;
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape" && !busy) setConfirm(null); };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [confirm, busy]);
  async function save() {
    setBusy(true); setError("");
    try { const data = await call("settings", "PATCH", { scopes }); setSettings(data); setScopes(data.scopes); toast.success(t("Dashboard-Einstellungen gespeichert.", "Dashboard settings saved.")); }
    catch (error) { setError(error instanceof Error ? error.message : "request_failed"); }
    finally { setBusy(false); }
  }
  async function revoke() {
    if (!confirm) return;
    const action = confirm; setBusy(true); setError("");
    try {
      await call(action === "all" ? "revoke-all" : "revoke-user", "POST", action === "all" ? {} : { user_id: userId });
      setConfirm(null);
      if (action === "all" || BigInt(userId) === BigInt(currentUserId)) await signOut({ callbackUrl: "/?error=SessionRevoked" });
      else { setUserId(""); toast.success(t("Alle Sitzungen dieses Nutzers wurden widerrufen.", "All sessions for this user have been revoked.")); }
    } catch (error) { setConfirm(null); setError(error instanceof Error ? error.message : "request_failed"); }
    finally { setBusy(false); }
  }
  const date = (milliseconds: number) => new Date(milliseconds).toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" });
  const labels: Record<string, [string, string]> = {
    identify: [t("Discord-Profil", "Discord profile"), t("Nutzer-ID, Name und Profilbild für die Anmeldung.", "User ID, name and avatar for sign-in.")],
    connections: [t("Verknüpfte Konten", "Connected accounts"), t("Freigegebene Kontoverknüpfungen für Louckup, zum Beispiel Steam oder Twitch.", "Authorized account connections for Louckup, such as Steam or Twitch.")],
    guilds: [t("Serverliste", "Guild list"), t("Server und Berechtigungen für Dashboard-Zugriffe und Verifizierung.", "Guilds and permissions for dashboard access and verification.")],
    "guilds.members.read": [t("Mitgliedschaftsdaten", "Membership details"), t("Eigene Rollen, Nickname und Beitrittsdatum auf freigegebenen Servern für Louckup.", "Own roles, nickname and join date in authorized guilds for Louckup.")],
  };
  return <section className="space-y-6 text-slate-200">
    <div className="flex items-center gap-4"><div className="rounded-2xl border border-blue-400/15 bg-blue-500/10 p-3 text-blue-400"><Settings2 className="h-6 w-6" /></div><div><p className="text-xs uppercase tracking-[0.2em] text-slate-500">{t("Owner-Bereich", "Owner area")}</p><h1 className="mt-1 text-2xl font-semibold tracking-tight">{t("Dashboard-Einstellungen", "Dashboard settings")}</h1></div></div>
    <p className="flex items-center gap-2 text-xs text-slate-500"><ShieldCheck className="h-4 w-4" />{t("Nur feste Owner-IDs · Einstellungen gelten für die gesamte Website", "Configured owner IDs only · Settings apply across the website")}</p>
    {loading ? <div className={`${card} flex items-center justify-center gap-3 py-16 text-slate-400`}><Loader2 className="h-5 w-5 animate-spin" />{t("Einstellungen werden geladen…", "Loading settings…")}</div> : settings && <>
      <div className={card}>
        <h2 className="flex items-center gap-2 text-base font-semibold"><KeyRound className="h-5 w-5 text-blue-400" />{t("OAuth-Berechtigungen", "OAuth permissions")}</h2>
        <p className="mt-2 text-sm leading-relaxed text-slate-400">{t("Wähle, welche Berechtigungen neue Dashboard-Anmeldungen und OAuth-Verifizierungen bei Discord anfragen.", "Choose which permissions new dashboard sign-ins and OAuth verifications request from Discord.")}</p>
        <div className="mt-5 divide-y divide-white/5">{all.map(scope => { const required = settings.required_scopes.includes(scope); return <div key={scope} className="flex items-start justify-between gap-5 py-4"><div><label htmlFor={`scope-${scope}`} className="text-sm font-medium">{labels[scope][0]}</label><p className="mt-1 font-mono text-[11px] text-blue-300">{scope}</p><p className="mt-2 text-xs leading-relaxed text-slate-500">{labels[scope][1]}</p>{required && <p className="mt-2 text-[11px] text-slate-400">{t("Für Anmeldung und Serverzugriff erforderlich", "Required for sign-in and guild access")}</p>}</div><Switch id={`scope-${scope}`} checked={scopes.includes(scope)} disabled={required || busy} onCheckedChange={checked => setScopes(current => all.filter(value => value === scope ? checked : current.includes(value)))} aria-label={labels[scope][0]} /></div>; })}</div>
        <div className="mt-4 rounded-xl bg-blue-500/5 p-3 text-xs leading-relaxed text-slate-400">{t("Die Auswahl wirkt beim nächsten Login oder der nächsten Verifizierung. Bereits erteilte Discord-Freigaben werden dadurch nicht widerrufen. Für eine neue Freigabe kannst du die Nutzer anschließend abmelden. guilds.join bleibt an die separate User-Pull-Funktion gebunden.", "The selection applies at the next sign-in or verification. It does not revoke permissions already granted in Discord. Sign users out afterwards if they should authorize again. guilds.join remains tied to the separate User Pull feature.")}</div>
        <div className="mt-5 flex flex-wrap items-center justify-between gap-4"><p className="text-xs text-slate-500">{settings.updated_at ? `${t("Zuletzt gespeichert", "Last saved")}: ${date(settings.updated_at * 1000)}` : t("Standardauswahl aktiv", "Default selection active")}</p><div className="flex gap-2">{dirty && <button onClick={() => setScopes(settings.scopes)} disabled={busy} className="rounded-xl border border-white/10 px-4 py-2.5 text-sm">{t("Zurücksetzen", "Reset")}</button>}<button onClick={save} disabled={!dirty || busy} className="flex items-center gap-2 rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-40">{busy && <Loader2 className="h-4 w-4 animate-spin" />}{t("Auswahl speichern", "Save selection")}</button></div></div>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <div className={card}><Users className="h-6 w-6 text-rose-400" /><h2 className="mt-4 text-base font-semibold">{t("Alle Nutzer abmelden", "Sign out all users")}</h2><p className="mt-2 text-sm leading-relaxed text-slate-400">{t("Widerruft alle bisherigen Dashboard-Sitzungen auf allen Geräten, einschließlich deiner eigenen. Danach können sich Nutzer erneut anmelden.", "Revokes all existing dashboard sessions on every device, including your own. Users can sign in again afterwards.")}</p><p className="mt-3 text-xs text-slate-500">{t("Zugriffe prüfen den Widerruf innerhalb von bis zu 15 Sekunden. Offene Tabs prüfen ihre Sitzung regelmäßig.", "Requests check revocation within up to 15 seconds. Open tabs check their session regularly.")}</p>{settings.revoked_before_ms > 0 && <p className="mt-3 text-xs text-slate-500">{t("Zuletzt ausgelöst", "Last triggered")}: {date(settings.revoked_before_ms)}</p>}<button onClick={() => setConfirm("all")} disabled={busy} className="mt-5 flex items-center gap-2 rounded-xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm font-medium text-rose-300 hover:bg-rose-500/15 disabled:opacity-40"><LogOut className="h-4 w-4" />{t("Alle abmelden", "Sign everyone out")}</button></div>
        <div className={card}><LogOut className="h-6 w-6 text-blue-400" /><h2 className="mt-4 text-base font-semibold">{t("Einzelnen Nutzer abmelden", "Sign out one user")}</h2><p className="mt-2 text-sm leading-relaxed text-slate-400">{t("Widerruft alle Dashboard-Sitzungen einer bestimmten Discord-ID auf allen Geräten.", "Revokes all dashboard sessions for one Discord ID on every device.")}</p><label htmlFor="logout-user-id" className="mt-5 block text-xs text-slate-400">{t("Discord-Nutzer-ID", "Discord user ID")}</label><input id="logout-user-id" value={userId} onChange={event => setUserId(event.target.value.replace(/[^0-9]/g, "").slice(0, 20))} inputMode="numeric" placeholder={t("Discord-ID eingeben", "Enter a Discord ID")} disabled={busy} className="mt-2 w-full rounded-xl border border-white/10 bg-black/20 px-4 py-3 font-mono text-sm outline-none focus:border-blue-400/60" /><button onClick={() => setConfirm("user")} disabled={busy || !/^[0-9]{17,20}$/.test(userId)} className="mt-4 rounded-xl border border-white/10 px-4 py-3 text-sm hover:bg-white/5 disabled:opacity-40">{t("Nutzer abmelden", "Sign user out")}</button></div>
      </div>
    </>}
    {error && <div role="alert" className="rounded-xl border border-rose-400/20 bg-rose-500/5 p-4 text-sm text-rose-300">{errorText(error)}</div>}
    {confirm && <div className="fixed inset-0 z-[10005] grid place-items-center bg-black/75 p-4 backdrop-blur-sm" onClick={() => { if (!busy) setConfirm(null); }}><div role="dialog" aria-modal="true" aria-labelledby="logout-confirm-title" className="w-full max-w-md rounded-2xl border border-white/10 cloudtix-admin-card bg-[#11151e] p-6 shadow-2xl" onClick={event => event.stopPropagation()}><div className="flex items-center justify-between gap-4"><h2 id="logout-confirm-title" className="text-lg font-semibold">{confirm === "all" ? t("Alle Sitzungen widerrufen?", "Revoke all sessions?") : t("Nutzer wirklich abmelden?", "Sign this user out?")}</h2><button onClick={() => setConfirm(null)} disabled={busy} aria-label={t("Schließen", "Close")} className="text-slate-400"><X className="h-5 w-5" /></button></div><p className="mt-4 text-sm leading-relaxed text-slate-400">{confirm === "all" ? t("Alle Nutzer einschließlich dir müssen sich neu anmelden. Bestehende Servereinstellungen bleiben erhalten.", "Every user, including you, must sign in again. Existing guild settings are retained.") : `${t("Alle Sitzungen dieser Discord-ID werden ungültig", "All sessions for this Discord ID will be invalidated")}: ${userId}`}</p><div className="mt-6 flex justify-end gap-3"><button onClick={() => setConfirm(null)} disabled={busy} className="rounded-xl border border-white/10 px-4 py-2.5 text-sm">{t("Abbrechen", "Cancel")}</button><button onClick={revoke} disabled={busy} autoFocus className="flex items-center gap-2 rounded-xl bg-rose-600 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-40">{busy && <Loader2 className="h-4 w-4 animate-spin" />}{t("Abmelden bestätigen", "Confirm sign-out")}</button></div></div></div>}
  </section>;
}
