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

/* ══════════════════════════════════════════════════════════════════════
   For staff
   ══════════════════════════════════════════════════════════════════════ */

export function PremiumKeysPanel() {
  const [keys, setKeys] = useState<any[]>([]);
  const [role, setRole] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [setup, setSetup] = useState({ pepper: true, token: true, url: true });
  const [loading, setLoading] = useState(true);

  const [days, setDays] = useState("30");
  const [recipient, setRecipient] = useState("");
  const [note, setNote] = useState("");
  const [amount, setAmount] = useState("1");
  const [minting, setMinting] = useState(false);
  // Shown once. Keys are stored hashed, so this is the only moment they
  // can ever be read.
  const [fresh, setFresh] = useState<{ keys: string[]; note: string } | null>(null);

  // Filtering and search, because a hundred rows of hashes is not a list
  // anybody can work with.
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await api.listPremiumKeys(200);
      setKeys(res?.keys || []);
      setRole(res?.role || null);
      setStats(res?.stats || null);
      setSetup({
        pepper: Boolean(res?.pepper_set),
        token: Boolean(res?.partner_token_set),
        url: Boolean(res?.template_url_set),
      });
    } catch (err: any) {
      toast.error(err?.message || "Keys konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const mint = async () => {
    const value = Number(days);
    if (Number.isNaN(value) || value < 0 || value > 3650) {
      toast.error("Laufzeit: 0 (unbegrenzt) bis 3650 Tage.");
      return;
    }
    const count = Math.max(1, Math.min(25, Number(amount) || 1));
    if (count > 1 && recipient.trim()) {
      toast.error("Mehrere Keys lassen sich nicht an eine Person schicken.");
      return;
    }
    if (recipient.trim() && !/^\d{15,25}$/.test(recipient.trim())) {
      toast.error("Die Benutzer-ID besteht nur aus Ziffern.");
      return;
    }

    setMinting(true);
    try {
      const made: string[] = [];
      let lastNote = "";
      for (let i = 0; i < count; i++) {
        const res = await api.createPremiumKey({
          days: value,
          user_id: recipient.trim() || undefined,
          note: note.trim() || undefined,
        });
        made.push(res.key);
        lastNote = res.result;
        if (res.delivery && res.delivery !== "sent" && res.delivery !== "none") {
          toast.warning(res.result);
        }
      }
      setFresh({
        keys: made,
        note: count > 1 ? `${count} Keys erstellt.` : lastNote,
      });
      if (count === 1 && !recipient.trim()) toast.success(lastNote);
      if (recipient.trim()) toast.success(lastNote);
      setRecipient("");
      setNote("");
      setAmount("1");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Key konnte nicht erstellt werden.");
    } finally {
      setMinting(false);
    }
  };

  const setRevoked = async (hash: string, undo: boolean) => {
    if (
      !undo &&
      !confirm(
        "Diesen Key sperren? Premium wird sofort entzogen — auch im " +
          "Template-Bot. Rückgängig machen ist möglich."
      )
    ) {
      return;
    }
    try {
      const res = await api.revokePremiumKey(hash, undo);
      toast.success(res?.result || (undo ? "Sperre aufgehoben." : "Key gesperrt."));
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Änderung fehlgeschlagen.");
    }
  };

  const remove = async (hash: string) => {
    if (
      !confirm(
        "Diesen Key ENDGÜLTIG löschen? Er verschwindet aus der Liste und " +
          "das lässt sich nicht rückgängig machen."
      )
    ) {
      return;
    }
    try {
      const res = await api.deletePremiumKey(hash);
      toast.success(res?.result || "Gelöscht.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Löschen fehlgeschlagen.");
    }
  };

  const purge = async (what: "revoked" | "expired" | "unclaimed") => {
    const labels = {
      revoked: "gesperrten",
      expired: "abgelaufenen",
      unclaimed: "nicht eingelösten",
    };
    if (!confirm(`Alle ${labels[what]} Keys endgültig löschen?`)) return;
    try {
      const res = await api.purgePremiumKeys(what);
      toast.success(res?.result || "Aufgeräumt.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Aufräumen fehlgeschlagen.");
    }
  };

  const now = Date.now();

  const stateOf = (k: any): KeyState => {
    if (k.revoked) return "revoked";
    if (!k.redeemed_by) return "unclaimed";
    if (k.expires_at && k.expires_at * 1000 <= now) return "expired";
    return "active";
  };

  const visible = keys.filter((k) => {
    if (filter !== "all" && stateOf(k) !== filter) return false;
    const needle = query.trim().toLowerCase();
    if (!needle) return true;
    return [k.redeemed_by, k.redeemed_name, k.note, k.key_hash]
      .filter(Boolean)
      .some((field: string) => String(field).toLowerCase().includes(needle));
  });

  return (
    <div className="space-y-5">
      {(!setup.pepper || !setup.token || !setup.url) && (
        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/[0.06] px-5 py-4">
          <p className="text-sm font-bold text-amber-300 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            Einrichtung unvollständig
          </p>
          <ul className="text-[12px] text-slate-400 mt-2 space-y-1">
            {!setup.pepper && (
              <li>
                &bull; <code>PREMIUM_KEY_PEPPER</code> fehlt &mdash; es lassen
                sich keine Keys erstellen. Wird der Wert später gesetzt,
                verfallen alle vorher erstellten Keys.
              </li>
            )}
            {!setup.token && (
              <li>
                &bull; <code>PREMIUM_PARTNER_TOKEN</code> fehlt &mdash; der
                Template-Bot kann nicht nachfragen, wer Premium hat.
              </li>
            )}
            {!setup.url && (
              <li>
                &bull; <code>TEMPLATE_BOT_URL</code> fehlt &mdash; Sperren und
                Freigeben wirken erst nach bis zu 5 Minuten statt sofort.
              </li>
            )}
          </ul>
        </div>
      )}

      {/* Numbers first: what is going on, at a glance. */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { label: "Aktiv", value: stats?.active ?? 0, tone: "text-emerald-300", hint: `${stats?.lifetime ?? 0} unbegrenzt` },
          { label: "Nicht eingelöst", value: stats?.unclaimed ?? 0, tone: "text-sky-300", hint: "warten auf Käufer" },
          { label: "Läuft bald ab", value: stats?.expiring_soon ?? 0, tone: "text-amber-300", hint: "in 7 Tagen" },
          { label: "Neu (30 Tage)", value: stats?.created_30d ?? 0, tone: "text-slate-200", hint: `${stats?.total ?? 0} insgesamt` },
        ].map((stat) => (
          <div
            key={stat.label}
            className="rounded-2xl border border-slate-800 bg-[#0d1b31]/60 px-5 py-4"
          >
            <p className={cn("text-2xl font-black tabular-nums", stat.tone)}>
              {stat.value}
            </p>
            <p className="text-[11px] text-slate-400 mt-0.5">{stat.label}</p>
            <p className="text-[10px] text-slate-600 mt-0.5">{stat.hint}</p>
          </div>
        ))}
      </div>

      <Section
        icon={ShieldCheck}
        title="Premium-Rolle"
        subtitle="Wird automatisch vergeben und wieder entzogen."
        tone="muted"
      >
        {!role?.configured ? (
          <p className="text-[12px] text-slate-500">
            Keine Rolle eingestellt. Unter <b>Bot Config &rarr; Premium Role</b>{" "}
            eine Rollen-ID eintragen, dann bekommt jeder mit gültiger Lizenz
            diese Rolle auf dem Support-Server.
          </p>
        ) : role?.ok ? (
          <p className="text-[12px] text-emerald-300">
            <b>{role.name}</b> &mdash; aktuell {role.members ?? 0} Mitglieder.
            Wird alle 10 Minuten abgeglichen.
          </p>
        ) : (
          <p className="text-[12px] text-amber-300">{role?.problem}</p>
        )}
      </Section>

      <Section icon={Plus} title="Keys erstellen" subtitle="Ersetzt den alten /key-Befehl.">
        <div className="grid sm:grid-cols-3 gap-3">
          <div className="space-y-1.5">
            <label
              htmlFor="premium-days"
              className="text-xs font-black uppercase tracking-widest text-slate-400"
            >
              Laufzeit (Tage)
            </label>
            <input
              id="premium-days"
              type="number"
              min={0}
              max={3650}
              className={INPUT}
              value={days}
              onChange={(e) => setDays(e.target.value)}
            />
            <div className="flex flex-wrap gap-1.5">
              {[
                { label: "30 T", value: "30" },
                { label: "90 T", value: "90" },
                { label: "1 Jahr", value: "365" },
                { label: "∞", value: "0" },
              ].map((preset) => (
                <button
                  key={preset.value}
                  onClick={() => setDays(preset.value)}
                  className={cn(
                    "px-2.5 py-1 rounded-lg text-[11px] font-bold border transition-colors",
                    days === preset.value
                      ? "bg-primary/15 border-primary/40 text-white"
                      : "bg-[#0a1628] border-slate-800 text-slate-400 hover:border-slate-700"
                  )}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="premium-amount"
              className="text-xs font-black uppercase tracking-widest text-slate-400"
            >
              Anzahl
            </label>
            <input
              id="premium-amount"
              type="number"
              min={1}
              max={25}
              className={INPUT}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
            <p className="text-[11px] text-slate-500">
              Mehrere auf einmal, z.B. für ein Gewinnspiel.
            </p>
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="premium-user"
              className="text-xs font-black uppercase tracking-widest text-slate-400"
            >
              Discord-ID (optional)
            </label>
            <input
              id="premium-user"
              className={INPUT}
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
              placeholder="Für DM-Versand"
              inputMode="numeric"
            />
            <p className="text-[11px] text-slate-500">
              Leer lassen, um selbst weiterzugeben.
            </p>
          </div>
        </div>

        <div className="space-y-1.5">
          <label
            htmlFor="premium-note"
            className="text-xs font-black uppercase tracking-widest text-slate-400"
          >
            Notiz (optional)
          </label>
          <input
            id="premium-note"
            className={INPUT}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="z.B. Bestellung #42"
          />
        </div>

        <button
          onClick={mint}
          disabled={minting || !setup.pepper}
          className="w-full py-3 rounded-xl bg-primary text-xs font-black uppercase tracking-widest hover:brightness-110 disabled:opacity-40 transition-all"
        >
          {minting ? "Wird erstellt …" : "Erstellen"}
        </button>

        {fresh && (
          <div className="rounded-2xl border border-amber-500/30 bg-amber-500/[0.06] px-5 py-4 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[12px] text-slate-300">{fresh.note}</p>
              <button
                onClick={() => setFresh(null)}
                className="text-[11px] text-slate-500 hover:text-white transition-colors"
              >
                ausblenden
              </button>
            </div>
            {fresh.keys.map((k) => (
              <div key={k} className="flex items-center gap-2">
                <code className="flex-1 font-mono text-sm text-white tracking-widest bg-[#0a1628] rounded-lg px-3 py-2 select-all">
                  {k}
                </code>
                <button
                  onClick={() => {
                    navigator.clipboard?.writeText(k);
                    toast.success("Kopiert.");
                  }}
                  className="p-2.5 rounded-lg bg-white/[0.03] border border-white/10 text-slate-400 hover:text-white transition-colors"
                  aria-label="Key kopieren"
                >
                  <Copy className="h-4 w-4" />
                </button>
              </div>
            ))}
            {fresh.keys.length > 1 && (
              <button
                onClick={() => {
                  navigator.clipboard?.writeText(fresh.keys.join("\n"));
                  toast.success("Alle kopiert.");
                }}
                className="text-[11px] font-bold text-amber-200 hover:text-white transition-colors"
              >
                Alle {fresh.keys.length} kopieren
              </button>
            )}
            <p className="text-[11px] text-amber-300">
              Jetzt notieren. Keys werden nur verschlüsselt gespeichert und
              lassen sich später nicht mehr anzeigen.
            </p>
          </div>
        )}
      </Section>

      <Section
        icon={KeyRound}
        title="Ausgegebene Keys"
        subtitle="Sperren entzieht Premium sofort. Löschen ist endgültig."
        action={
          <button
            onClick={load}
            className="p-2 rounded-lg text-slate-500 hover:text-white hover:bg-white/[0.04] transition-colors"
            aria-label="Liste neu laden"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          {(
            [
              ["all", "Alle", keys.length],
              ["active", "Aktiv", stats?.active ?? 0],
              ["unclaimed", "Offen", stats?.unclaimed ?? 0],
              ["expired", "Abgelaufen", stats?.expired ?? 0],
              ["revoked", "Gesperrt", stats?.revoked ?? 0],
            ] as [Filter, string, number][]
          ).map(([id, label, count]) => (
            <button
              key={id}
              onClick={() => setFilter(id)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-[11px] font-bold border transition-colors",
                filter === id
                  ? "bg-primary/15 border-primary/40 text-white"
                  : "bg-[#0a1628] border-slate-800 text-slate-400 hover:border-slate-700"
              )}
            >
              {label} <span className="text-slate-500">{count}</span>
            </button>
          ))}
        </div>

        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-600" />
          <input
            className={cn(INPUT, "pl-10")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Nach Name, ID oder Notiz suchen"
            aria-label="Keys durchsuchen"
          />
        </div>

        {loading ? (
          <p className="text-[12px] text-slate-500">Wird geladen …</p>
        ) : visible.length === 0 ? (
          <p className="text-[12px] text-slate-500">
            {keys.length === 0
              ? "Noch keine Keys erstellt."
              : "Nichts gefunden."}
          </p>
        ) : (
          <div className="space-y-2">
            {visible.map((k) => {
              const state = stateOf(k);
              const badge = {
                revoked: { label: "Gesperrt", tone: "text-red-300 bg-red-500/10" },
                expired: { label: "Abgelaufen", tone: "text-slate-400 bg-slate-500/10" },
                active: { label: "Aktiv", tone: "text-emerald-300 bg-emerald-500/10" },
                unclaimed: { label: "Offen", tone: "text-sky-300 bg-sky-500/10" },
              }[state];
              const left = daysLeft(k.expires_at);

              return (
                <div
                  key={k.key_hash}
                  className="flex items-center gap-3 rounded-xl bg-[#0a1628] border border-slate-800 px-4 py-3"
                >
                  <span
                    className={cn(
                      "text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-md shrink-0",
                      badge.tone
                    )}
                  >
                    {badge.label}
                  </span>

                  <div className="min-w-0 flex-1">
                    <p className="text-[12px] text-slate-300 truncate">
                      {k.redeemed_by
                        ? k.redeemed_name
                          ? `${k.redeemed_name} (${k.redeemed_by})`
                          : k.redeemed_by
                        : "Noch nicht eingelöst"}
                    </p>
                    <p className="text-[11px] text-slate-500 mt-0.5 truncate">
                      {k.duration === 0 ? "unbegrenzt" : `${k.duration} Tage`}
                      {k.expires_at ? ` · bis ${formatDate(k.expires_at)}` : ""}
                      {state === "active" && left !== null && left <= 7
                        ? ` · noch ${left} ${left === 1 ? "Tag" : "Tage"}`
                        : ""}
                      {k.note ? ` · ${k.note}` : ""}
                    </p>
                  </div>

                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => setRevoked(k.key_hash, Boolean(k.revoked))}
                      className={cn(
                        "p-2 rounded-lg transition-colors",
                        k.revoked
                          ? "text-slate-500 hover:text-emerald-300 hover:bg-emerald-500/10"
                          : "text-slate-500 hover:text-amber-300 hover:bg-amber-500/10"
                      )}
                      aria-label={k.revoked ? "Sperre aufheben" : "Key sperren"}
                      title={k.revoked ? "Sperre aufheben" : "Key sperren"}
                    >
                      {k.revoked ? (
                        <Undo2 className="h-4 w-4" />
                      ) : (
                        <Ban className="h-4 w-4" />
                      )}
                    </button>
                    <button
                      onClick={() => remove(k.key_hash)}
                      className="p-2 rounded-lg text-slate-600 hover:text-red-300 hover:bg-red-500/10 transition-colors"
                      aria-label="Key endgültig löschen"
                      title="Endgültig löschen"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Section>

      <Section
        icon={Trash2}
        title="Aufräumen"
        subtitle="Löscht Gruppen endgültig. Aktive Lizenzen sind nie dabei."
        tone="muted"
      >
        <div className="grid sm:grid-cols-3 gap-2">
          {(
            [
              ["revoked", "Gesperrte löschen", stats?.revoked ?? 0],
              ["expired", "Abgelaufene löschen", stats?.expired ?? 0],
              ["unclaimed", "Nicht eingelöste löschen", stats?.unclaimed ?? 0],
            ] as ["revoked" | "expired" | "unclaimed", string, number][]
          ).map(([what, label, count]) => (
            <button
              key={what}
              onClick={() => purge(what)}
              disabled={count === 0}
              className="py-3 px-3 rounded-xl bg-red-500/[0.06] border border-red-500/20 text-[11px] font-black uppercase tracking-widest text-red-300 hover:bg-red-500/10 disabled:opacity-30 disabled:hover:bg-red-500/[0.06] transition-all"
            >
              {label} ({count})
            </button>
          ))}
        </div>
      </Section>
    </div>
  );
}
