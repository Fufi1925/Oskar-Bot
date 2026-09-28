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
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string>("");

  const load = async () => {
    try {
      const data = await api.getOwnerPrivileges(currentUserId);
      setOwners(data.owners || []);
    } catch (error: any) {
      toast.error(error?.message || "Owner-Rechte konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentUserId]);

  const toggle = async (owner: OwnerEntry, key: PrivilegeKey) => {
    const marker = `${owner.user_id}:${key}`;
    const privileges = { ...owner.privileges, [key]: !owner.privileges[key] };
    setBusy(marker);
    try {
      const result = await api.updateOwnerPrivileges(
        owner.user_id,
        currentUserId,
        privileges,
      );
      setOwners((current) =>
        current.map((entry) =>
          entry.user_id === owner.user_id
            ? { ...entry, privileges: result.privileges }
            : entry,
        ),
      );
      toast.success("Owner-Recht gespeichert.");
    } catch (error: any) {
      toast.error(error?.message || "Owner-Recht konnte nicht gespeichert werden.");
    } finally {
      setBusy("");
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[320px] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <section className="space-y-6">
      <div className="rounded-3xl border border-amber-400/20 bg-[#131318] p-6">
        <div className="flex items-start gap-4">
          <div className="rounded-2xl bg-amber-400/10 p-3 text-amber-300">
            <LockKeyhole className="h-6 w-6" />
          </div>
          <div>
            <h2 className="text-xl font-black text-white">Owner-Sonderrechte</h2>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">
              Dieser Reiter ist ausschließlich für IDs aus OWNER_IDS sichtbar. Normale
              Adminrechte bleiben unverändert; hier werden nur besondere Bypässe pro
              Owner-ID gesteuert. Jede eingetragene Owner-ID darf diese Schalter verwalten.
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-5">
        {owners.map((owner) => (
          <article
            key={owner.user_id}
            className="overflow-hidden rounded-3xl border border-slate-800 bg-[#101014]"
          >
            <header className="flex flex-wrap items-center gap-4 border-b border-slate-800 p-5">
              {owner.avatar ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={owner.avatar}
                  alt=""
                  className="h-12 w-12 rounded-2xl border border-white/10"
                />
              ) : (
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-400/10">
                  <Crown className="h-5 w-5 text-amber-300" />
                </div>
              )}
              <div className="min-w-0">
                <p className="truncate font-black text-white">
                  {owner.username || "Unbekannter Owner"}
                </p>
                <code className="text-xs text-slate-500">{owner.user_id}</code>
              </div>
              {owner.user_id === currentUserId && (
                <span className="ml-auto rounded-lg border border-emerald-400/20 bg-emerald-400/10 px-2 py-1 text-[10px] font-black uppercase tracking-widest text-emerald-300">
                  Du
                </span>
              )}
            </header>

            <div className="grid gap-3 p-5 lg:grid-cols-2">
              {PRIVILEGES.map((privilege) => {
                const Icon = privilege.icon;
                const enabled = Boolean(owner.privileges?.[privilege.key]);
                const marker = `${owner.user_id}:${privilege.key}`;
                return (
                  <button
                    key={privilege.key}
                    type="button"
                    disabled={Boolean(busy)}
                    onClick={() => toggle(owner, privilege.key)}
                    className={cn(
                      "flex items-center gap-3 rounded-2xl border p-4 text-left transition disabled:opacity-50",
                      enabled
                        ? "border-amber-400/25 bg-amber-400/[0.07]"
                        : "border-slate-800 bg-[#131318] hover:border-slate-700",
                    )}
                  >
                    <span
                      className={cn(
                        "rounded-xl p-2",
                        enabled ? "bg-amber-400/10 text-amber-300" : "bg-white/[0.04] text-slate-500",
                      )}
                    >
                      {busy === marker ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Icon className="h-4 w-4" />
                      )}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-bold text-white">{privilege.label}</span>
                      <span className="mt-1 block text-xs leading-5 text-slate-500">
                        {privilege.description}
                      </span>
                    </span>
                    <span
                      className={cn(
                        "relative h-6 w-11 shrink-0 rounded-full transition",
                        enabled ? "bg-amber-400" : "bg-slate-700",
                      )}
                    >
                      <span
                        className={cn(
                          "absolute top-1 h-4 w-4 rounded-full bg-white transition-all",
                          enabled ? "left-6" : "left-1",
                        )}
                      />
                    </span>
                  </button>
                );
              })}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
