"use client";

import { Link2, ShieldCheck, Users } from "lucide-react";
import { useWebsiteLocale } from "@/lib/i18n/locale";

type Connection = { id: string; name?: string; type: string; verified?: boolean; visibility?: number; friend_sync?: boolean; show_activity?: boolean; two_way_link?: boolean };
type Membership = { guild_id: string; nick?: string; avatar?: string; joined_at?: string; premium_since?: string; communication_disabled_until?: string; roles: string[]; pending?: boolean; deaf?: boolean; mute?: boolean; flags?: number };
export type OwnerOAuthSnapshot = {
  source: string; captured_at: number; expires_at: number; complete: boolean; scopes: string[];
  profile: Record<string, string | number | boolean>;
  guilds: { id: string; name: string; icon: string | null; owner: boolean; permissions: string }[];
  connections?: Connection[]; memberships?: Membership[];
  connections_complete?: boolean; memberships_complete?: boolean;
  collection_status?: "collecting" | "ready" | "partial";
};

export function OwnerOAuthDetails({ snapshot, filter }: { snapshot: OwnerOAuthSnapshot; filter: string }) {
  const locale = useWebsiteLocale();
  const t = (de: string, en: string) => locale === "en-GB" ? en : de;
  const card = "rounded-2xl border border-white/[0.07] cloudtix-workspace-card bg-[#11151e] p-5 sm:p-6";
  const field = (label: string, value: React.ReactNode) => <div className="min-w-0"><dt className="text-xs text-slate-500">{label}</dt><dd className="mt-1 break-words text-sm text-slate-200">{value ?? "—"}</dd></div>;
  const bool = (value?: boolean) => value === undefined ? "—" : value ? t("Ja", "Yes") : t("Nein", "No");
  const date = (value?: string) => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" }) : "—";
  const names = new Map(snapshot.guilds.map(guild => [guild.id, guild.name]));
  const query = filter.trim().toLocaleLowerCase();
  const memberships = (snapshot.memberships || []).filter(member => `${names.get(member.guild_id) || ""} ${member.guild_id} ${member.nick || ""}`.toLocaleLowerCase().includes(query));
  const descriptions: Record<string, string> = {
    identify: t("Discord-Profil und Konto-ID", "Discord profile and account ID"),
    connections: t("Verknüpfte Konten und ihre Freigabeeinstellungen", "Connected accounts and their sharing settings"),
    guilds: t("Serverliste, Inhaberschaft und Serverberechtigungen", "Guild list, ownership and guild permissions"),
    "guilds.members.read": t("Eigene Mitgliedschaften: Rollen, Nickname und Beitrittsdatum", "Own memberships: roles, nickname and join date"),
    "guilds.join": t("Beitritt über die ausdrücklich aktivierte User-Pull-Funktion", "Joining through the expressly enabled User Pull feature"),
  };
  return <>
    <div className={card}>
      <h3 className="flex items-center gap-2 text-sm font-semibold"><ShieldCheck className="h-4 w-4 text-blue-400" />{t("Freigegebene OAuth-Berechtigungen", "Granted OAuth permissions")}</h3>
      <dl className="mt-4 grid gap-4 sm:grid-cols-2">{snapshot.scopes.map(scope => <div key={scope}><dt className="font-mono text-xs text-blue-300">{scope}</dt><dd className="mt-1 text-xs leading-relaxed text-slate-400">{descriptions[scope] || scope}</dd></div>)}</dl>
      {snapshot.collection_status === "collecting" && <p role="status" className="mt-4 rounded-xl bg-blue-500/5 p-3 text-xs text-blue-300">{t("Zusatzdaten werden im Hintergrund abgerufen. Suche die ID erneut, um den aktuellen Stand zu sehen.", "Additional data is being collected in the background. Search the ID again to see the latest results.")}</p>}
      {snapshot.collection_status === "partial" && <p className="mt-4 text-xs text-amber-300">{t("Ein Teil der freigegebenen Daten konnte nicht abgerufen werden. Leere Felder bedeuten nicht, dass keine Daten vorhanden sind.", "Some authorized data could not be retrieved. Empty fields do not mean that no data exists.")}</p>}
    </div>
    <div className={card}>
      <h3 className="flex items-center gap-2 text-sm font-semibold"><Link2 className="h-4 w-4 text-blue-400" />{t("Verknüpfte Konten", "Connected accounts")} <span className="text-slate-500">({(snapshot.connections || []).length})</span></h3>
      {!snapshot.scopes.includes("connections") ? <p className="mt-3 text-sm text-slate-500">{t("Diese Berechtigung wurde noch nicht freigegeben. Daten erscheinen nach einer neuen Anmeldung oder Verifizierung.", "This permission has not been granted yet. Data appears after a new sign-in or verification.")}</p> : <>
        <p className="mt-2 text-xs text-slate-500">{snapshot.connections_complete ? t("Vollständig abgerufen bei der letzten Freigabe.", "Fully retrieved at the last authorization.") : t("Abruf noch nicht vollständig abgeschlossen.", "Collection has not completed in full yet.")}</p>
        <div className="mt-4 divide-y divide-white/5">{(snapshot.connections || []).map((connection, index) => <div key={`${connection.type}-${connection.id}-${index}`} className="py-4 first:pt-0">
          <p className="break-words text-sm font-medium">{connection.name || connection.id} <span className="text-xs font-normal text-slate-500">· {connection.type}</span></p>
          <dl className="mt-3 grid gap-4 sm:grid-cols-3">{field(t("Konto-ID", "Account ID"), connection.id)}{field(t("Von Discord bestätigt", "Verified by Discord"), bool(connection.verified))}{field(t("Im Profil sichtbar", "Visible on profile"), connection.visibility === undefined ? "—" : bool(connection.visibility === 1))}{field(t("Freunde synchronisieren", "Sync friends"), bool(connection.friend_sync))}{field(t("Aktivität anzeigen", "Show activity"), bool(connection.show_activity))}{field(t("Beidseitige Verknüpfung", "Two-way connection"), bool(connection.two_way_link))}</dl>
        </div>)}</div>
        {!snapshot.connections?.length && <p className="mt-4 text-sm text-slate-500">{snapshot.connections_complete ? t("Keine verknüpften Konten von Discord zurückgegeben.", "Discord returned no connected accounts.") : t("Noch keine Kontodaten verfügbar.", "No account data is available yet.")}</p>}
      </>}
    </div>
    <div className={card}>
      <h3 className="flex items-center gap-2 text-sm font-semibold"><Users className="h-4 w-4 text-blue-400" />{t("OAuth-Mitgliedschaftsdaten", "OAuth membership details")} <span className="text-slate-500">({(snapshot.memberships || []).length})</span></h3>
      {!snapshot.scopes.includes("guilds.members.read") ? <p className="mt-3 text-sm text-slate-500">{t("Diese Berechtigung wurde noch nicht freigegeben. Daten erscheinen nach einer neuen Anmeldung oder Verifizierung.", "This permission has not been granted yet. Data appears after a new sign-in or verification.")}</p> : <>
        <p className="mt-2 text-xs text-slate-500">{snapshot.memberships_complete ? t("Mitgliedschaften aller abgerufenen Server vollständig eingelesen.", "Memberships for all retrieved guilds have been collected in full.") : t("Mitgliedschaftsdaten teilweise verfügbar oder noch im Abruf.", "Membership details are partially available or still being collected.")}</p>
        <div className="mt-4 divide-y divide-white/5">{memberships.map(member => <details key={member.guild_id} className="py-4 first:pt-0">
          <summary className="cursor-pointer text-sm font-medium"><span className="break-words">{names.get(member.guild_id) || t("Servermitgliedschaft", "Guild membership")}</span></summary>
          <p className="mt-3 font-mono text-[11px] text-slate-500">{member.guild_id}</p>
          <dl className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{field(t("Server-Nickname", "Server nickname"), member.nick)}{field(t("Beigetreten", "Joined"), date(member.joined_at))}{field(t("Boost seit", "Boosting since"), date(member.premium_since))}{field(t("Mitgliedschaft noch ausstehend", "Membership pending"), bool(member.pending))}{field(t("Stummgeschaltet", "Muted"), bool(member.mute))}{field(t("Taubgeschaltet", "Deafened"), bool(member.deaf))}{field(t("Timeout bis", "Timed out until"), date(member.communication_disabled_until))}{field(t("Mitgliedschafts-Flags", "Membership flags"), member.flags)}{field(t("Server-Avatar-ID", "Guild avatar ID"), member.avatar)}</dl>
          <p className="mt-4 text-xs text-slate-500">{t("Rollen-IDs", "Role IDs")}</p><div className="mt-2 flex flex-wrap gap-2">{member.roles.length ? member.roles.map(role => <span key={role} className="rounded-md bg-white/5 px-2 py-1 font-mono text-[11px] text-slate-300">{role}</span>) : <span className="text-xs text-slate-500">{t("Keine zusätzlichen Rollen", "No additional roles")}</span>}</div>
        </details>)}</div>
        {!memberships.length && <p className="mt-4 text-sm text-slate-500">{t("Keine passenden Mitgliedschaftsdaten verfügbar.", "No matching membership details available.")}</p>}
      </>}
    </div>
  </>;
}
