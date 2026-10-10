"use client";

import React, { useEffect, useState } from "react";
import {
  Crown,
  FlaskConical,
  Gauge,
  Gem,
  Loader2,
  LockKeyhole,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useUnsavedGuard } from "@/components/dashboard/save-bar";

type PrivilegeKey =
  | "guild_owner_bypass"
  | "premium_bypass"
  | "beta_bypass"
  | "maintenance_bypass"
  | "security_bypass"
  | "limits_bypass";

type OwnerEntry = {
  user_id: string;
  username: string | null;
  avatar: string | null;
  privileges: Record<PrivilegeKey, boolean>;
};

const PRIVILEGES: Array<{
  key: PrivilegeKey;
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  {
    key: "guild_owner_bypass",
    label: "Inhaber-Bypass",
    description:
      "Darf Bereiche sehen und Aktionen ausführen, die sonst ausschließlich dem tatsächlichen Discord-Serverinhaber vorbehalten sind.",
    icon: Crown,
  },
  {
    key: "premium_bypass",
    label: "Premium-Bypass",
    description: "Kann nutzergebundene Premium-Funktionen ohne aktives Premium verwenden.",
    icon: Gem,
  },
  {
    key: "beta_bypass",
    label: "Beta-Bypass",
    description: "Kann geschlossene Beta-Befehle und Beta-Funktionen verwenden.",
    icon: FlaskConical,
  },
  {
    key: "maintenance_bypass",
    label: "Wartungs-Bypass",
    description: "Bleibt bei Wartung, globaler Befehlssperre und Notfallsperre handlungsfähig.",
    icon: Wrench,
  },
  {
    key: "security_bypass",
    label: "Sicherheits-Bypass",
    description: "Wird bei Bot-Befehlen nicht durch globale Nutzer- oder Server-Blacklists blockiert.",
    icon: ShieldCheck,
  },
  {
    key: "limits_bypass",
    label: "Limit-Bypass",
    description: "Darf speziell geschützte Mengen-, Ticket- und Aktionslimits überschreiten.",
    icon: Gauge,
  },
];

export function OwnerPrivilegesPanel({ currentUserId }: { currentUserId: string }) {
  const [owners, setOwners] = useState<OwnerEntry[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState<Record<PrivilegeKey, boolean> | null>(null);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const owner = owners.find((entry) => entry.user_id === selectedId);
  const changed = Boolean(owner && draft && PRIVILEGES.some(({ key }) => Boolean(draft[key]) !== Boolean(owner.privileges[key])));
  useUnsavedGuard(changed || busy, () => toast.error("Bitte Änderungen zuerst speichern oder verwerfen."));
  const filtered = owners.filter((entry) => `${entry.username || ""} ${entry.user_id}`.toLowerCase().includes(query.toLowerCase()));
  const activeCount = (entry: OwnerEntry) => PRIVILEGES.filter(({ key }) => entry.privileges[key]).length;

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setOwners([]);
    setDraft(null);
    api.getOwnerPrivileges(currentUserId).then((data) => {
      if (!active) return;
      const entries: OwnerEntry[] = data.owners || [];
      const selected = entries.find((entry) => entry.user_id === currentUserId) || entries[0];
      setOwners(entries);
      setSelectedId(selected?.user_id || "");
      setDraft(selected ? { ...selected.privileges } : null);
    }).catch((failure: unknown) => {
      if (active) setError(failure instanceof Error ? failure.message : "Owner-Rechte konnten nicht geladen werden.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [currentUserId, reload]);

  const save = async () => {
    if (!owner || !draft || busy) return;
    setBusy(true);
    try {
      const result = await api.updateOwnerPrivileges(owner.user_id, currentUserId, draft);
      setOwners((entries) => entries.map((entry) => entry.user_id === owner.user_id ? { ...entry, privileges: result.privileges } : entry));
      setDraft({ ...result.privileges });
      toast.success("Owner-Rechte gespeichert.");
    } catch (failure: unknown) {
      toast.error(failure instanceof Error ? failure.message : "Speichern fehlgeschlagen. Deine Änderungen bleiben erhalten.");
    } finally { setBusy(false); }
  };

  if (loading) return <div role="status" className="flex min-h-[320px] items-center justify-center gap-3 text-slate-400"><Loader2 className="h-5 w-5 animate-spin" />Owner-Rechte werden geladen …</div>;
  if (error) return <div role="alert" className="rounded-2xl border border-red-400/20 bg-red-400/5 p-6 text-sm text-red-300">{error}<button type="button" onClick={() => setReload((value) => value + 1)} className="ml-3 rounded-lg border border-red-300/20 px-3 py-2">Erneut laden</button></div>;

  return (
    <section className="space-y-6">
      <header className="rounded-2xl border border-white/10 cloudtix-admin-card bg-[#131318] p-5 sm:p-7">
        <div className="flex items-center gap-3"><LockKeyhole className="h-6 w-6 text-amber-300" /><h2 className="text-xl font-bold text-white">Owner-Extra</h2><button type="button" disabled={changed || busy} onClick={() => setReload((value) => value + 1)} className="ml-auto rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 disabled:opacity-40">Aktualisieren</button></div>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">Sonderrechte gezielt pro Owner verwalten. Wähle eine Person, prüfe die Ausnahmen und speichere deine Änderungen gemeinsam.</p>
        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {[['Owner', owners.length], ['Aktive Ausnahmen', owners.reduce((sum, entry) => sum + activeCount(entry), 0)], ['Rechte pro Owner', PRIVILEGES.length]].map(([label, value]) => <div key={label} className="rounded-xl bg-white/[0.03] p-3"><p className="text-xs text-slate-400">{label}</p><p className="mt-1 text-2xl font-semibold text-white">{value}</p></div>)}
        </div>
      </header>
      {owners.length === 0 ? <p className="rounded-2xl border border-white/10 p-6 text-slate-400">Keine Owner verfügbar.</p> : (
        <div className="grid items-start gap-5 lg:grid-cols-[260px_minmax(0,1fr)]">
          <aside className="rounded-2xl border border-white/10 cloudtix-admin-card bg-[#131318] p-4">
            <label htmlFor="owner-search" className="mb-2 block text-xs font-medium text-slate-400">Owner suchen</label>
            <input id="owner-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name oder Discord-ID" className="w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-amber-300/50" />
            <div className="mt-3 space-y-2">
              {filtered.map((entry) => <button key={entry.user_id} type="button" disabled={busy || changed} aria-pressed={selectedId === entry.user_id} onClick={() => { setSelectedId(entry.user_id); setDraft({ ...entry.privileges }); }} className={cn("w-full rounded-xl border p-3 text-left transition disabled:opacity-60", selectedId === entry.user_id ? "border-amber-300/30 bg-amber-300/5" : "border-transparent hover:bg-white/5")}>
                <span className="block truncate text-sm font-semibold text-white">{entry.username || "Owner"}{entry.user_id === currentUserId ? " · Du" : ""}</span>
                <span className="block break-all text-xs text-slate-500">{entry.user_id}</span><span className="mt-2 block text-xs text-slate-400">{activeCount(entry)} von {PRIVILEGES.length} Ausnahmen aktiv</span>
              </button>)}
              {filtered.length === 0 && <p className="p-3 text-sm text-slate-400">Keine passenden Owner.</p>}
            </div>
            {changed && <p className="mt-3 text-xs leading-5 text-amber-300">Speichere oder verwirf deine Änderungen, bevor du die Person wechselst.</p>}
          </aside>
          {owner && draft && <article className="overflow-hidden rounded-2xl border border-white/10 cloudtix-admin-field bg-[#101014]">
            <header className="flex flex-wrap items-center gap-3 border-b border-white/10 p-5">
              <Crown className="h-6 w-6 text-amber-300" /><div className="min-w-0 flex-1"><h3 className="truncate font-semibold text-white">{owner.username || "Owner"}</h3><p className="break-all text-xs text-slate-400">{owner.user_id}</p></div>
              <button type="button" onClick={() => { navigator.clipboard.writeText(owner.user_id).then(() => toast.success("Discord-ID kopiert.")).catch(() => toast.error("Kopieren nicht möglich.")); }} className="rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 hover:bg-white/5">ID kopieren</button>
            </header>
            <div className="divide-y divide-white/5">
              {PRIVILEGES.map(({ key, label, description, icon: Icon }) => <div key={key} className="flex items-start gap-3 p-5">
                <Icon className="mt-1 h-5 w-5 shrink-0 text-slate-400" /><div className="min-w-0 flex-1"><p id={`owner-${key}`} className="text-sm font-semibold text-white">{label}</p><p id={`owner-${key}-help`} className="mt-1 text-xs leading-5 text-slate-400">{description}</p></div>
                <button type="button" role="switch" aria-checked={Boolean(draft[key])} aria-labelledby={`owner-${key}`} aria-describedby={`owner-${key}-help`} disabled={busy} onClick={() => setDraft({ ...draft, [key]: !draft[key] })} className={cn("relative mt-1 h-6 w-11 shrink-0 rounded-full transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-300 focus-visible:ring-offset-2 focus-visible:ring-offset-black disabled:opacity-50", draft[key] ? "bg-amber-400" : "bg-slate-700")}><span className={cn("absolute top-1 h-4 w-4 rounded-full bg-white transition-all", draft[key] ? "left-6" : "left-1")} /></button>
              </div>)}
            </div>
            <footer className="space-y-3 border-t border-white/10 bg-white/[0.02] p-5">
              <p className="text-xs leading-5 text-slate-400">Sicherheits- und Limit-Ausnahmen nur aktivieren, wenn sie für diese Person benötigt werden.</p>
              <div className="flex flex-wrap items-center gap-2">
                <button type="button" disabled={busy} onClick={() => setDraft(Object.fromEntries(PRIVILEGES.map(({ key }) => [key, false])) as Record<PrivilegeKey, boolean>)} className="rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 disabled:opacity-50">Alle Ausnahmen deaktivieren</button>
                <span role="status" className="mr-auto text-xs text-slate-400">{changed ? "Ungespeicherte Änderungen" : "Alle Änderungen gespeichert"}</span>
                <button type="button" disabled={busy || !changed} onClick={() => setDraft({ ...owner.privileges })} className="rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-300 disabled:opacity-40">Verwerfen</button>
                <button type="button" disabled={busy || !changed} onClick={save} className="inline-flex items-center gap-2 rounded-lg bg-amber-300 px-4 py-2 text-sm font-semibold text-black disabled:opacity-40">{busy && <Loader2 className="h-4 w-4 animate-spin" />}Speichern</button>
              </div>
            </footer>
          </article>}
        </div>
      )}
    </section>
  );
}
