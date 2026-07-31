"use client";

/**
 * The Premium tab.
 *
 * Two products, deliberately unequal:
 *
 *   Main bot      — nothing to sell yet, so it says "coming soon" and
 *                   offers no field. A disabled input that pretends to
 *                   do something is worse than an honest placeholder.
 *   Template bot  — a licence key bought in Discord, typed in here.
 *
 * The key is bound to the signed-in Discord account. The account id is
 * never sent from here: the proxy fills it in from the session, so the
 * form cannot activate premium onto somebody else's id.
 */

import React, { useCallback, useEffect, useState } from "react";
import { Gem, Clock, Check, KeyRound, Trash2 } from "lucide-react";
import { useSession } from "next-auth/react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const INPUT =
  "w-full bg-[#0a1628] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white " +
  "placeholder:text-slate-600 focus:border-primary/50 focus:outline-none transition-colors";

function formatDate(seconds?: number | null): string {
  if (!seconds) return "";
  return new Date(seconds * 1000).toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function Card({
  icon: Icon,
  title,
  subtitle,
  accent,
  children,
}: {
  icon: any;
  title: string;
  subtitle: string;
  accent?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-[#0d1b31]/60 border border-slate-800 rounded-3xl p-6 space-y-5">
      <header className="flex items-start gap-3">
        <div
          className={cn(
            "h-10 w-10 rounded-2xl grid place-items-center shrink-0",
            accent || "bg-primary/10"
          )}
        >
          <Icon className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h3 className="text-base font-bold text-white">{title}</h3>
          <p className="text-[12px] text-slate-400 mt-0.5">{subtitle}</p>
        </div>
      </header>
      {children}
    </section>
  );
}

export function PremiumPanel() {
  const { data: session } = useSession();
  const userId = session?.user?.id;

  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    try {
      setStatus(await api.getMyPremium(userId));
    } catch (err: any) {
      toast.error(err?.message || "Status konnte nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    load();
  }, [load]);

  const redeem = async () => {
    if (!key.trim()) {
      toast.error("Bitte einen Key eingeben.");
      return;
    }
    setBusy(true);
    try {
      const res = await api.redeemKey(key.trim());
      toast.success(res?.result || "Key eingelöst.");
      setKey("");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Der Key konnte nicht eingelöst werden.");
    } finally {
      setBusy(false);
    }
  };

  const template = status?.template_bot;
  const active = Boolean(template?.premium);

  return (
    <div className="space-y-6 max-w-3xl">
      <Card
        icon={Gem}
        title="University Bot Premium"
        subtitle="Zusatzfunktionen für diesen Bot."
      >
        <div className="rounded-2xl border border-dashed border-slate-700 bg-[#0a1628] px-5 py-8 text-center">
          <Clock className="h-6 w-6 text-slate-500 mx-auto" />
          <p className="text-sm font-bold text-slate-300 mt-3">Coming Soon</p>
          <p className="text-[12px] text-slate-500 mt-1">
            Für den Haupt-Bot gibt es noch kein Premium. Sobald es so weit
            ist, steht es hier.
          </p>
        </div>
      </Card>

      <Card
        icon={KeyRound}
        title="Template-Bot Premium"
        subtitle="Lizenz-Key eingeben, den du in Discord gekauft hast."
      >
        {loading ? (
          <p className="text-[12px] text-slate-500">Wird geladen …</p>
        ) : active ? (
          <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/[0.06] px-5 py-4">
            <p className="text-sm font-bold text-emerald-300 flex items-center gap-2">
              <Check className="h-4 w-4" />
              Premium ist aktiv
            </p>
            <p className="text-[12px] text-slate-400 mt-1">
              {template?.lifetime
                ? "Unbegrenzt gültig."
                : `Gültig bis ${formatDate(template?.expires_at)}.`}
            </p>
          </div>
        ) : (
          <div className="rounded-2xl border border-slate-800 bg-[#0a1628] px-5 py-4">
            <p className="text-sm font-bold text-slate-300">
              Kein Premium aktiv
            </p>
            <p className="text-[12px] text-slate-500 mt-1">
              Key im Support-Server kaufen, dann hier eintragen.
            </p>
          </div>
        )}

        <div className="space-y-2">
          <label className="text-xs font-black uppercase tracking-widest text-slate-400">
            Lizenz-Key
          </label>
          <div className="flex flex-col sm:flex-row gap-2">
            <input
              className={cn(INPUT, "font-mono tracking-widest uppercase")}
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="XXXX-XXXX-XXXX-XXXX"
              maxLength={40}
              spellCheck={false}
              aria-label="Lizenz-Key eingeben"
            />
            <button
              onClick={redeem}
              disabled={busy || !userId}
              className="px-6 py-3 rounded-xl bg-primary text-xs font-black uppercase tracking-widest shrink-0 hover:brightness-110 disabled:opacity-40 transition-all"
            >
              {busy ? "Prüfen …" : "Einlösen"}
            </button>
          </div>
          <p className="text-[11px] text-slate-500">
            Der Key wird fest mit deinem Discord-Konto verbunden und lässt
            sich danach nicht mehr übertragen. Groß- und Kleinschreibung
            sowie Bindestriche sind egal.
          </p>
        </div>
      </Card>
    </div>
  );
}

/**
 * Key management for staff. Only hashes are stored, so this can list
 * and revoke keys but never show one — a lost key gets revoked and
 * replaced, it cannot be looked up.
 */
export function PremiumKeysPanel() {
  const [keys, setKeys] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.listPremiumKeys(100);
      setKeys(res?.keys || []);
    } catch (err: any) {
      toast.error(err?.message || "Keys konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const revoke = async (hash: string) => {
    if (!confirm("Diesen Key sperren? Das lässt sich nicht rückgängig machen.")) return;
    try {
      await api.revokePremiumKey(hash);
      toast.success("Key gesperrt.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Sperren fehlgeschlagen.");
    }
  };

  return (
    <Card
      icon={KeyRound}
      title="Ausgegebene Keys"
      subtitle="Mit /key create auf dem Support-Server erstellen."
    >
      {loading ? (
        <p className="text-[12px] text-slate-500">Wird geladen …</p>
      ) : keys.length === 0 ? (
        <p className="text-[12px] text-slate-500">
          Noch keine Keys erstellt.
        </p>
      ) : (
        <div className="space-y-2">
          {keys.map((k) => (
            <div
              key={k.key_hash}
              className="flex items-center gap-3 rounded-xl bg-[#0a1628] border border-slate-800 px-4 py-3"
            >
              <div className="min-w-0 flex-1">
                <p className="text-[12px] font-mono text-slate-400 truncate">
                  {k.key_hash.slice(0, 16)}…
                </p>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  {k.revoked
                    ? "Gesperrt"
                    : k.redeemed_by
                    ? `Eingelöst von ${k.redeemed_by}`
                    : "Noch nicht eingelöst"}
                  {" · "}
                  {k.duration === 0 ? "unbegrenzt" : `${k.duration} Tage`}
                  {k.expires_at ? ` · bis ${formatDate(k.expires_at)}` : ""}
                </p>
              </div>
              {!k.revoked && (
                <button
                  onClick={() => revoke(k.key_hash)}
                  className="p-2 rounded-lg text-slate-500 hover:text-red-300 hover:bg-red-500/10 transition-colors"
                  aria-label="Key sperren"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
