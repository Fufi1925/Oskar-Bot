"use client";

/**
 * Premium — what the customer sees.
 *
 * Rebuilt. The previous version was three cards of the same weight, so
 * the one thing that matters ("do I have premium, until when") had to be
 * hunted for among equally loud boxes, and nothing moved when the page
 * opened.
 *
 * The shape now follows the state, because there are only two:
 *
 *   no licence  → a hero that says so, then the redeem field
 *   licence     → a gold hero with the expiry and a progress bar, then
 *                 the invite link that makes the licence useful
 *
 * The redeem form disappears once there is nothing to redeem, and the
 * invite link does not exist before there is. Showing either at the
 * wrong moment is how a page ends up saying the same thing to everyone.
 *
 * The main bot has nothing to sell, so it gets an honest placeholder
 * instead of a disabled form pretending otherwise.
 *
 * The account id is never sent from here. The proxy fills it in from the
 * session, so a key can only ever be bound to whoever is signed in.
 *
 * Staff tooling lives in premium-admin.tsx.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Check, Clock, ExternalLink, Gem, KeyRound, RefreshCw, Sparkles,
} from "lucide-react";
import { useSession } from "next-auth/react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CountUp, Reveal, useReducedMotion } from "@/components/ui/reveal";

const INPUT =
  "w-full bg-[#0e0e12] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white " +
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

/**
 * Format a key as the user types: uppercase, in blocks of four.
 *
 * People paste these from a DM on a phone, where autocorrect and stray
 * spaces are the norm. Fixing it while typing means the field always
 * looks like the key in the message, so a mistake is visible before the
 * button is pressed rather than after.
 */
function tidyKey(raw: string): string {
  const clean = (raw || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 16);
  return clean.replace(/(.{4})(?=.)/g, "$1-");
}

function Card({
  icon: Icon,
  title,
  subtitle,
  children,
  tone = "plain",
}: {
  icon: any;
  title: string;
  subtitle?: string;
  children?: React.ReactNode;
  tone?: "plain" | "muted";
}) {
  return (
    <section
      className={cn(
        "rounded-3xl border p-6 space-y-5",
        tone === "muted"
          ? "border-slate-800/70 bg-[#0e0e12]/40"
          : "border-slate-800 bg-[#0e0e12]/60"
      )}
    >
      <header className="flex items-start gap-3">
        <div className="h-10 w-10 rounded-2xl bg-primary/10 grid place-items-center shrink-0">
          <Icon className="h-5 w-5 text-primary" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-bold text-white">{title}</h3>
          {subtitle && (
            <p className="text-[12px] text-slate-400 mt-0.5">{subtitle}</p>
          )}
        </div>
      </header>
      {children}
    </section>
  );
}

/** A skeleton, so the page has the same shape before and after loading. */
function Skeleton() {
  return (
    <div className="space-y-5" aria-busy="true" aria-label="Wird geladen">
      <div className="rounded-3xl border border-slate-800 bg-[#0e0e12]/60 p-6">
        <div className="flex items-center gap-4">
          <div className="h-14 w-14 rounded-2xl bg-slate-800/60 animate-pulse" />
          <div className="space-y-2 flex-1">
            <div className="h-4 w-40 rounded bg-slate-800/60 animate-pulse" />
            <div className="h-3 w-64 rounded bg-slate-800/40 animate-pulse" />
          </div>
        </div>
      </div>
      <div className="rounded-3xl border border-slate-800 bg-[#0e0e12]/60 p-6 space-y-4">
        <div className="h-4 w-48 rounded bg-slate-800/60 animate-pulse" />
        <div className="h-11 w-full rounded-xl bg-slate-800/40 animate-pulse" />
      </div>
    </div>
  );
}

export function PremiumPanel() {
  const { data: session } = useSession();
  const userId = session?.user?.id;
  const reduced = useReducedMotion();

  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  // Set for one beat right after a successful redeem, so the hero can
  // celebrate instead of silently swapping colour.
  const [justRedeemed, setJustRedeemed] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(
    async (quiet = false) => {
      if (!userId) return;
      if (quiet) setRefreshing(true);
      try {
        setStatus(await api.getMyPremium(userId));
      } catch (err: any) {
        toast.error(err?.message || "Status konnte nicht geladen werden.");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [userId]
  );

  useEffect(() => {
    load();
  }, [load]);

  const redeem = async () => {
    const cleaned = key.replace(/-/g, "");
    if (!cleaned) {
      toast.error("Bitte einen Key eingeben.");
      inputRef.current?.focus();
      return;
    }
    // Say it here rather than after a round trip: the length is the one
    // mistake we can catch without asking the server.
    if (cleaned.length !== 16) {
      toast.error(`Ein Key hat 16 Zeichen — dieser hat ${cleaned.length}.`);
      inputRef.current?.focus();
      return;
    }

    setBusy(true);
    try {
      const res = await api.redeemKey(key.trim());
      toast.success(res?.result || "Key eingelöst.");
      setKey("");
      setJustRedeemed(true);
      await load();
      window.setTimeout(() => setJustRedeemed(false), 2200);
    } catch (err: any) {
      toast.error(err?.message || "Der Key konnte nicht eingelöst werden.");
      inputRef.current?.focus();
    } finally {
      setBusy(false);
    }
  };

  const template = status?.template_bot;
  const active = Boolean(template?.premium);
  const left = daysLeft(template?.expires_at);
  // Läuft das Premium über die kostenlose Probewoche des
  // Template-Bots? Dann muss das auch dastehen: „Premium ist aktiv“
  // allein liest sich wie etwas Bezahltes, und der Nutzer wundert
  // sich, wenn es nach sieben Tagen weg ist.
  const trial = Boolean(template?.via_trial);
  const complete = key.replace(/-/g, "").length === 16;

  // How much of the licence is left, as a bar. Only meaningful when the
  // duration is known, so a lifetime licence gets no bar at all rather
  // than a full one that never moves.
  let progress: number | null = null;
  if (active && !template?.lifetime && left !== null && template?.duration_days) {
    progress = Math.max(0, Math.min(100, (left / template.duration_days) * 100));
  }

  if (loading) return <Skeleton />;

  return (
    <div className="space-y-5">
      {/* One card, two possible statements. Nothing else competes. */}
      <Reveal>
        <section
          className={cn(
            "relative overflow-hidden rounded-3xl border p-6 transition-colors duration-700",
            active
              ? "border-amber-500/30 bg-gradient-to-br from-amber-500/[0.12] via-amber-500/[0.03] to-transparent"
              : "border-slate-800 bg-[#0e0e12]/60"
          )}
        >
          {/* A single sweep on the moment of success. Not a loop: this
              is a one-off event, and a permanent shimmer would just be
              noise on a page people leave open. */}
          {justRedeemed && !reduced && (
            <span
              aria-hidden
              className="pointer-events-none absolute inset-y-0 -left-1/3 w-1/3 premium-celebrate"
            />
          )}

          <div className="flex items-start gap-4">
            <div
              className={cn(
                "h-14 w-14 rounded-2xl grid place-items-center shrink-0 transition-all duration-700",
                active
                  ? "bg-amber-500/20 scale-100"
                  : "bg-slate-800/60 scale-95"
              )}
            >
              <Gem
                className={cn(
                  "h-7 w-7 transition-colors duration-700",
                  active ? "text-amber-300" : "text-slate-500"
                )}
              />
            </div>

            <div className="min-w-0 flex-1">
              <p
                className={cn(
                  "text-lg font-black transition-colors duration-700",
                  active ? "text-amber-200" : "text-white"
                )}
              >
                {active
                  ? trial
                    ? `${template?.trial?.duration_days ?? 7} Tage Premium – kostenlos`
                    : "Premium ist aktiv"
                  : "Kein Premium"}
              </p>

              {active ? (
                <p className="text-[13px] text-slate-300 mt-1">
                  {trial ? (
                    <>
                      Deine Probewoche läuft noch bis{" "}
                      <span className="font-bold text-white">
                        {formatDate(template?.expires_at)}
                      </span>
                      {left !== null && (
                        <span className="text-slate-400">
                          {" "}
                          &middot;{" "}
                          <CountUp
                            value={left}
                            className="font-bold text-white tabular-nums"
                          />{" "}
                          {left === 1 ? "Tag" : "Tage"} übrig
                        </span>
                      )}
                      . Danach brauchst du einen Key — die Probewoche gibt
                      es nur einmal pro Konto.
                    </>
                  ) : template?.lifetime ? (
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
                          &middot; noch{" "}
                          <CountUp
                            value={left}
                            className="font-bold text-white tabular-nums"
                          />{" "}
                          {left === 1 ? "Tag" : "Tage"}
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

              {progress !== null && (
                <div className="mt-3 h-1.5 rounded-full bg-slate-800/80 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-amber-400 to-amber-300 transition-[width] duration-1000 ease-out"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              )}
            </div>

            <button
              onClick={() => load(true)}
              disabled={refreshing}
              className="p-2 rounded-lg text-slate-500 hover:text-white hover:bg-white/[0.04] transition-colors shrink-0 disabled:opacity-50"
              aria-label="Status neu laden"
              title="Status neu laden"
            >
              <RefreshCw
                className={cn("h-4 w-4", refreshing && "animate-spin")}
              />
            </button>
          </div>

          {/* Only once active: the link that makes the licence useful. */}
          {active && status?.template_invite && (
            <Reveal delay={120}>
              <div className="mt-5 pt-5 border-t border-amber-500/15 space-y-2">
                <a
                  href={status.template_invite}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-amber-500/15 border border-amber-500/30 text-xs font-black uppercase tracking-widest text-amber-100 hover:bg-amber-500/25 hover:border-amber-500/50 transition-all"
                >
                  <ExternalLink className="h-3.5 w-3.5 transition-transform group-hover:-translate-y-0.5" />
                  Template-Bot zum Server hinzufügen
                </a>
                <p className="text-[11px] text-slate-400">
                  Premium hängt an deinem Konto, nicht an einem Server. Du
                  kannst den Bot auf jeden Server holen &mdash; er erkennt
                  dich dort sofort, ohne dass du den Key erneut eingibst.
                </p>
              </div>
            </Reveal>
          )}
        </section>
      </Reveal>

      {/* Gone once there is nothing left to redeem. */}
      {!active && (
        <Reveal delay={80}>
          <Card
            icon={KeyRound}
            title="Lizenz-Key einlösen"
            subtitle="Für die Premium-Vorlagen des Template-Bots."
          >
            <div className="flex flex-col sm:flex-row gap-2">
              <div className="relative flex-1">
                <input
                  ref={inputRef}
                  className={cn(
                    INPUT,
                    "font-mono tracking-[0.25em] uppercase pr-11",
                    complete && "border-emerald-500/40"
                  )}
                  value={key}
                  onChange={(e) => setKey(tidyKey(e.target.value))}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") redeem();
                  }}
                  placeholder="XXXX-XXXX-XXXX-XXXX"
                  maxLength={19}
                  spellCheck={false}
                  autoComplete="off"
                  aria-label="Lizenz-Key eingeben"
                />
                {complete && (
                  <Check className="absolute right-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-emerald-400" />
                )}
              </div>
              <button
                onClick={redeem}
                disabled={busy || !userId}
                className="px-7 py-3 rounded-xl bg-primary text-xs font-black uppercase tracking-widest shrink-0 hover:brightness-110 active:scale-[0.98] disabled:opacity-40 transition-all"
              >
                {busy ? "Prüfen …" : "Einlösen"}
              </button>
            </div>

            {/* Sixteen dots that fill as you type. Better than a counter:
                you see at a glance whether the key is complete. */}
            <div className="flex items-center gap-2">
              <div className="flex gap-1" aria-hidden>
                {Array.from({ length: 16 }).map((_, index) => (
                  <span
                    key={index}
                    className={cn(
                      "h-1 w-3 rounded-full transition-colors duration-200",
                      index < key.replace(/-/g, "").length
                        ? complete
                          ? "bg-emerald-400"
                          : "bg-primary"
                        : "bg-slate-800"
                    )}
                  />
                ))}
              </div>
              <span className="text-[11px] text-slate-500 tabular-nums">
                {key.replace(/-/g, "").length}/16
              </span>
            </div>

            <p className="text-[11px] text-slate-500">
              Groß- und Kleinschreibung sowie Bindestriche sind egal. Der Key
              wird beim Einlösen fest mit deinem Discord-Konto verbunden.
            </p>
          </Card>
        </Reveal>
      )}

      {/* Nothing to sell yet, so nothing is offered. */}
      <Reveal delay={active ? 80 : 160}>
        <Card
          icon={Sparkles}
          title="University Bot Premium"
          subtitle="Zusatzfunktionen für diesen Bot."
          tone="muted"
        >
          <div className="flex items-center gap-3 rounded-2xl border border-dashed border-slate-700/70 bg-[#0e0e12]/60 px-5 py-4">
            <Clock className="h-5 w-5 text-slate-500 shrink-0" />
            <div>
              <p className="text-sm font-bold text-slate-300">Coming Soon</p>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Hier gibt es noch nichts zu kaufen. Sobald es so weit ist,
                steht es an dieser Stelle.
              </p>
            </div>
          </div>
        </Card>
      </Reveal>
    </div>
  );
}
