"use client";

/**
 * Premium.
 *
 * Written from scratch. The first version was a stack of grey boxes that
 * said the same thing whether or not you had a licence, and the state
 * that actually matters — do I have premium, until when — was a line of
 * small text among many.
 *
 * Now the page leads with one card that can only say one of two things,
 * and everything else follows from that:
 *
 *   no licence  -> the field to redeem one, and nothing else
 *   licence     -> until when, and the invite link to use it
 *
 * The main bot has nothing to sell, so it gets an honest placeholder
 * rather than a disabled form pretending otherwise.
 *
 * The account id is never sent from here. The proxy fills it in from the
 * session, so a key can only ever be bound to whoever is signed in.
 *
 * Staff tooling lives in premium-admin.tsx — the two audiences want
 * different things and sharing one file made both worse.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  Gem, Clock, Check, KeyRound, Trash2, ExternalLink, Plus, Undo2,
  AlertTriangle, ShieldCheck, Copy, Sparkles, RefreshCw, Search, Ban,
} from "lucide-react";
import { useSession } from "next-auth/react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/** The four states a key can be in. */
type KeyState = "active" | "unclaimed" | "expired" | "revoked";
/** Which rows the admin list is showing. */
type Filter = "all" | KeyState;

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

/** Days left, or null when it never expires. */
function daysLeft(seconds?: number | null): number | null {
  if (!seconds) return null;
  return Math.max(0, Math.ceil((seconds * 1000 - Date.now()) / 86_400_000));
}

function Section({
  icon: Icon,
  title,
  subtitle,
  children,
  tone = "plain",
  action,
}: {
  icon: any;
  title: string;
  subtitle?: string;
  children?: React.ReactNode;
  tone?: "plain" | "gold" | "muted";
  action?: React.ReactNode;
}) {
  return (
    <section
      className={cn(
        "rounded-3xl border p-6 space-y-5",
        tone === "gold"
          ? "border-amber-500/25 bg-gradient-to-b from-amber-500/[0.07] to-transparent"
          : tone === "muted"
          ? "border-slate-800/70 bg-[#0d1b31]/40"
          : "border-slate-800 bg-[#0d1b31]/60"
      )}
    >
      <header className="flex items-start gap-3">
        <div
          className={cn(
            "h-10 w-10 rounded-2xl grid place-items-center shrink-0",
            tone === "gold" ? "bg-amber-500/15" : "bg-primary/10"
          )}
        >
          <Icon
            className={cn(
              "h-5 w-5",
              tone === "gold" ? "text-amber-300" : "text-primary"
            )}
          />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-bold text-white">{title}</h3>
          {subtitle && (
            <p className="text-[12px] text-slate-400 mt-0.5">{subtitle}</p>
          )}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════════
   For the customer
   ══════════════════════════════════════════════════════════════════════ */

export function PremiumPanel() {
  const { data: session } = useSession();
  const userId = session?.user?.id;

  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!userId) return;
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
  const left = daysLeft(template?.expires_at);

  if (loading) {
    return (
      <div className="rounded-3xl border border-slate-800 bg-[#0d1b31]/60 p-6">
        <p className="text-[12px] text-slate-500">Wird geladen …</p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* The one thing worth knowing, said once and clearly. */}
      <section
        className={cn(
          "rounded-3xl border p-6",
          active
            ? "border-amber-500/30 bg-gradient-to-br from-amber-500/[0.10] via-amber-500/[0.03] to-transparent"
            : "border-slate-800 bg-[#0d1b31]/60"
        )}
      >
        <div className="flex items-start gap-4">
          <div
            className={cn(
              "h-14 w-14 rounded-2xl grid place-items-center shrink-0",
              active ? "bg-amber-500/20" : "bg-slate-800/60"
            )}
          >
            <Gem
              className={cn(
                "h-7 w-7",
                active ? "text-amber-300" : "text-slate-500"
              )}
            />
          </div>

          <div className="min-w-0 flex-1">
            <p
              className={cn(
                "text-lg font-black",
                active ? "text-amber-200" : "text-white"
              )}
            >
              {active ? "Premium ist aktiv" : "Kein Premium"}
            </p>

            {active ? (
              <p className="text-[13px] text-slate-300 mt-1">
                {template?.lifetime ? (
                  <>Unbegrenzt gültig &mdash; läuft nicht ab.</>
                ) : (
                  <>
                    Gültig bis{" "}
                    <span className="font-bold text-white">
                      {formatDate(template?.expires_at)}
                    </span>
                    {left !== null && (
                      <span className="text-slate-400">
                        {" "}
                        &middot; noch {left} {left === 1 ? "Tag" : "Tage"}
                      </span>
                    )}
                  </>
                )}
              </p>
            ) : (
              <p className="text-[13px] text-slate-400 mt-1">
                Kauf dir im Support-Server einen Lizenz-Key und trage ihn
                unten ein.
              </p>
            )}
          </div>

          <button
            onClick={load}
            className="p-2 rounded-lg text-slate-500 hover:text-white hover:bg-white/[0.04] transition-colors shrink-0"
            aria-label="Status neu laden"
            title="Status neu laden"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>

        {/* Only once it is active: the link that makes the licence useful. */}
        {active && status?.template_invite && (
          <div className="mt-5 pt-5 border-t border-amber-500/15 space-y-2">
            <a
              href={status.template_invite}
              target="_blank"
              rel="noopener noreferrer"
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-amber-500/15 border border-amber-500/30 text-xs font-black uppercase tracking-widest text-amber-100 hover:bg-amber-500/25 transition-all"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Template-Bot zum Server hinzufügen
            </a>
            <p className="text-[11px] text-slate-400">
              Premium hängt an deinem Konto, nicht an einem Server. Du kannst
              den Bot auf jeden Server holen &mdash; er erkennt dich dort
              sofort, ohne dass du den Key erneut eingibst.
            </p>
          </div>
        )}
      </section>

      {/* The form disappears once there is nothing to redeem. */}
      {!active && (
        <Section
          icon={KeyRound}
          title="Lizenz-Key einlösen"
          subtitle="Für die Premium-Vorlagen des Template-Bots."
        >
          <div className="flex flex-col sm:flex-row gap-2">
            <input
              className={cn(INPUT, "font-mono tracking-[0.2em] uppercase")}
              value={key}
              onChange={(e) => setKey(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") redeem();
              }}
              placeholder="XXXX-XXXX-XXXX-XXXX"
              maxLength={40}
              spellCheck={false}
              aria-label="Lizenz-Key eingeben"
            />
            <button
              onClick={redeem}
              disabled={busy || !userId}
              className="px-7 py-3 rounded-xl bg-primary text-xs font-black uppercase tracking-widest shrink-0 hover:brightness-110 disabled:opacity-40 transition-all"
            >
              {busy ? "Prüfen …" : "Einlösen"}
            </button>
          </div>
          <p className="text-[11px] text-slate-500">
            Groß- und Kleinschreibung sowie Bindestriche sind egal. Der Key
            wird beim Einlösen fest mit deinem Discord-Konto verbunden.
          </p>
        </Section>
      )}

      {/* Nothing to sell yet, so nothing is offered. */}
      <Section
        icon={Sparkles}
        title="University Bot Premium"
        subtitle="Zusatzfunktionen für diesen Bot."
        tone="muted"
      >
        <div className="flex items-center gap-3 rounded-2xl border border-dashed border-slate-700/70 bg-[#0a1628]/60 px-5 py-4">
          <Clock className="h-5 w-5 text-slate-500 shrink-0" />
          <div>
            <p className="text-sm font-bold text-slate-300">Coming Soon</p>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Hier gibt es noch nichts zu kaufen. Sobald es so weit ist,
              steht es an dieser Stelle.
            </p>
          </div>
        </div>
      </Section>
    </div>
  );
}
