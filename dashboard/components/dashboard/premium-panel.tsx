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
import {
  Gem, Clock, Check, KeyRound, Trash2, ExternalLink, Plus, Undo2,
  AlertTriangle, ShieldCheck, Copy,
} from "lucide-react";
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
          <div className="space-y-3">
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

            {/* Only once premium is active. The licence follows the
                account, so the bot can be added to any server at any
                time and will recognise the buyer there straight away. */}
            {status?.template_invite && (
              <a
                href={status.template_invite}
                target="_blank"
                rel="noopener noreferrer"
                className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-primary/10 border border-primary/30 text-xs font-black uppercase tracking-widest text-white hover:bg-primary/20 transition-all"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                Template-Bot zum Server hinzufügen
              </a>
            )}
            <p className="text-[11px] text-slate-500">
              Premium hängt an deinem Konto, nicht am Server. Du kannst den
              Bot auf jeden Server holen &mdash; er erkennt dich dort
              sofort, ohne dass du den Key erneut eingibst.
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
  const [role, setRole] = useState<any>(null);
  const [setup, setSetup] = useState<{ pepper: boolean; token: boolean }>({
    pepper: true,
    token: true,
  });
  const [loading, setLoading] = useState(true);

  const [days, setDays] = useState("30");
  const [recipient, setRecipient] = useState("");
  const [note, setNote] = useState("");
  const [minting, setMinting] = useState(false);
  // The freshly minted key, shown once. It is stored hashed, so this is
  // the only moment it can ever be read.
  const [fresh, setFresh] = useState<{ key: string; note: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.listPremiumKeys(100);
      setKeys(res?.keys || []);
      setRole(res?.role || null);
      setSetup({
        pepper: Boolean(res?.pepper_set),
        token: Boolean(res?.partner_token_set),
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
    if (recipient.trim() && !/^\d{15,25}$/.test(recipient.trim())) {
      toast.error("Die Benutzer-ID besteht nur aus Ziffern.");
      return;
    }

    setMinting(true);
    try {
      const res = await api.createPremiumKey({
        days: value,
        user_id: recipient.trim() || undefined,
        note: note.trim() || undefined,
      });
      setFresh({ key: res.key, note: res.result });
      if (res.delivery === "sent") toast.success(res.result);
      else toast.warning(res.result);
      setRecipient("");
      setNote("");
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
      !confirm("Diesen Key sperren? Premium wird damit sofort entzogen.")
    ) {
      return;
    }
    try {
      await api.revokePremiumKey(hash, undo);
      toast.success(undo ? "Sperre aufgehoben." : "Key gesperrt.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Änderung fehlgeschlagen.");
    }
  };

  const active = keys.filter(
    (k) => k.redeemed_by && !k.revoked && (!k.expires_at || k.expires_at * 1000 > Date.now())
  ).length;
  const open = keys.filter((k) => !k.redeemed_by && !k.revoked).length;

  return (
    <div className="space-y-6">
      {(!setup.pepper || !setup.token) && (
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
          </ul>
        </div>
      )}

      <Card
        icon={ShieldCheck}
        title="Premium-Rolle"
        subtitle="Wird automatisch vergeben und wieder entzogen."
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
            Die Rolle wird alle 10 Minuten abgeglichen.
          </p>
        ) : (
          <p className="text-[12px] text-amber-300">{role?.problem}</p>
        )}
      </Card>

      <Card
        icon={Plus}
        title="Key erstellen"
        subtitle="Ersetzt den alten /key-Befehl."
      >
        <div className="grid sm:grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <label
              htmlFor="premium-days"
              className="text-xs font-black uppercase tracking-widest text-slate-400"
            >
              Laufzeit in Tagen
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
            <p className="text-[11px] text-slate-500">
              0 = unbegrenzt. Die Zeit läuft ab dem Einlösen, nicht ab jetzt.
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
              Leer lassen, um den Key selbst weiterzugeben.
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
          {minting ? "Wird erstellt …" : "Key erstellen"}
        </button>

        {fresh && (
          <div className="rounded-2xl border border-primary/30 bg-primary/[0.06] px-5 py-4 space-y-2">
            <p className="text-[12px] text-slate-300">{fresh.note}</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 font-mono text-sm text-white tracking-widest bg-[#0a1628] rounded-lg px-3 py-2 select-all">
                {fresh.key}
              </code>
              <button
                onClick={() => {
                  navigator.clipboard?.writeText(fresh.key);
                  toast.success("Kopiert.");
                }}
                className="p-2.5 rounded-lg bg-white/[0.03] border border-white/10 text-slate-400 hover:text-white transition-colors"
                aria-label="Key kopieren"
              >
                <Copy className="h-4 w-4" />
              </button>
            </div>
            <p className="text-[11px] text-amber-300">
              Jetzt notieren. Der Key wird nur verschlüsselt gespeichert und
              lässt sich später nicht mehr anzeigen.
            </p>
          </div>
        )}
      </Card>

      <Card
        icon={KeyRound}
        title="Ausgegebene Keys"
        subtitle={`${active} aktiv · ${open} noch nicht eingelöst · ${keys.length} insgesamt`}
      >
        {loading ? (
          <p className="text-[12px] text-slate-500">Wird geladen …</p>
        ) : keys.length === 0 ? (
          <p className="text-[12px] text-slate-500">Noch keine Keys erstellt.</p>
        ) : (
          <div className="space-y-2">
            {keys.map((k) => {
              const expired =
                k.expires_at && k.expires_at * 1000 <= Date.now();
              return (
                <div
                  key={k.key_hash}
                  className="flex items-center gap-3 rounded-xl bg-[#0a1628] border border-slate-800 px-4 py-3"
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-[12px] text-slate-300 truncate">
                      {k.redeemed_by
                        ? k.redeemed_name
                          ? `${k.redeemed_name} (${k.redeemed_by})`
                          : k.redeemed_by
                        : "Noch nicht eingelöst"}
                    </p>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      {k.revoked
                        ? "Gesperrt"
                        : expired
                        ? "Abgelaufen"
                        : k.redeemed_by
                        ? "Aktiv"
                        : "Offen"}
                      {" · "}
                      {k.duration === 0 ? "unbegrenzt" : `${k.duration} Tage`}
                      {k.expires_at ? ` · bis ${formatDate(k.expires_at)}` : ""}
                      {k.note ? ` · ${k.note}` : ""}
                    </p>
                    <p className="text-[10px] font-mono text-slate-600 mt-0.5 truncate">
                      {k.key_hash.slice(0, 16)}…
                    </p>
                  </div>
                  <button
                    onClick={() => setRevoked(k.key_hash, Boolean(k.revoked))}
                    className={cn(
                      "p-2 rounded-lg transition-colors",
                      k.revoked
                        ? "text-slate-500 hover:text-emerald-300 hover:bg-emerald-500/10"
                        : "text-slate-500 hover:text-red-300 hover:bg-red-500/10"
                    )}
                    aria-label={k.revoked ? "Sperre aufheben" : "Key sperren"}
                    title={k.revoked ? "Sperre aufheben" : "Key sperren"}
                  >
                    {k.revoked ? (
                      <Undo2 className="h-4 w-4" />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
