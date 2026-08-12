"use client";

/**
 * Premium — the admin view.
 *
 * Rebuilt from nothing. The previous version was a column of cards you
 * had to read top to bottom, and the list underneath showed four fields
 * out of the eleven the API returns. Answering "when did this person
 * buy, and when did they redeem it" meant looking in the database.
 *
 * What drove this layout:
 *
 *   * The list is the tab. Everything else is either a number above it
 *     or a form you open when you need it — minting is rare, looking
 *     something up is constant.
 *   * Every field the API sends is reachable. Dates and the hash live
 *     in a row you expand, so the common case stays one line per key.
 *   * Bulk work is selection-based. Fifty expired keys used to be fifty
 *     confirmations, or one purge button with no way to look first.
 *   * Nothing is invented. Every value here comes from the API; where
 *     something is unknown it says so instead of guessing.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, ArrowUpDown, Ban, CheckCircle2, ChevronDown, Copy,
  Download, KeyRound, Plus, RefreshCw, Search, ShieldCheck, Trash2,
  Undo2, X,
} from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CountUp, Reveal } from "@/components/ui/reveal";

/* ── types ─────────────────────────────────────────────────────────── */

type KeyState = "active" | "unclaimed" | "expired" | "revoked";
type Filter = "all" | KeyState;
type SortBy = "created" | "expires" | "state";

interface KeyRow {
  key_hash: string;
  product: string;
  duration: number;
  created_at: number | null;
  created_by: string | null;
  created_name: string;
  note: string;
  redeemed_by: string | null;
  redeemed_name: string;
  redeemed_at: number | null;
  expires_at: number | null;
  revoked: number;
}

/* ── helpers ───────────────────────────────────────────────────────── */

const INPUT =
  "w-full bg-[#0e0e12] border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-white " +
  "placeholder:text-slate-600 focus:border-primary/50 focus:outline-none transition-colors";

const STATES: Record<KeyState, { label: string; dot: string; chip: string }> = {
  active: {
    label: "Aktiv",
    dot: "bg-emerald-400",
    chip: "text-emerald-300 bg-emerald-500/10 border-emerald-500/20",
  },
  unclaimed: {
    label: "Offen",
    dot: "bg-sky-400",
    chip: "text-sky-300 bg-sky-500/10 border-sky-500/20",
  },
  expired: {
    label: "Abgelaufen",
    dot: "bg-slate-500",
    chip: "text-slate-400 bg-slate-500/10 border-slate-600/20",
  },
  revoked: {
    label: "Gesperrt",
    dot: "bg-red-400",
    chip: "text-red-300 bg-red-500/10 border-red-500/20",
  },
};

function stateOf(row: KeyRow, now: number): KeyState {
  if (row.revoked) return "revoked";
  if (!row.redeemed_by) return "unclaimed";
  if (row.expires_at && row.expires_at * 1000 <= now) return "expired";
  return "active";
}

function fmtDate(seconds?: number | null): string {
  if (!seconds) return "—";
  return new Date(seconds * 1000).toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function fmtDateTime(seconds?: number | null): string {
  if (!seconds) return "—";
  return new Date(seconds * 1000).toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** "noch 12 Tage", or null when it never ends. */
function remaining(seconds?: number | null): number | null {
  if (!seconds) return null;
  return Math.max(0, Math.ceil((seconds * 1000 - Date.now()) / 86_400_000));
}

/** Who this key belongs to, in the most useful form available. */
function ownerLabel(row: KeyRow): string {
  if (!row.redeemed_by) return "—";
  return row.redeemed_name
    ? `${row.redeemed_name} · ${row.redeemed_by}`
    : row.redeemed_by;
}

/* ── small pieces ──────────────────────────────────────────────────── */

function Stat({
  label,
  value,
  hint,
  tone,
  active,
  onClick,
}: {
  label: string;
  value: number;
  hint: string;
  tone: string;
  active?: boolean;
  onClick?: () => void;
}) {
  // The numbers double as filters — seeing "7 expired" and having to
  // then find the filter for it is a step nobody should need.
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      onClick={onClick}
      className={cn(
        "text-left rounded-2xl border px-4 py-3.5 transition-all",
        active
          ? "border-primary/40 bg-primary/[0.08]"
          : "border-slate-800 bg-[#0e0e12]/60",
        onClick && "hover:border-slate-700"
      )}
    >
      <p className={cn("text-2xl font-black tabular-nums", tone)}>
        <CountUp value={value} />
      </p>
      <p className="text-[11px] text-slate-400 mt-0.5">{label}</p>
      <p className="text-[10px] text-slate-600 mt-0.5">{hint}</p>
    </Tag>
  );
}

function Panel({
  icon: Icon,
  title,
  subtitle,
  right,
  children,
  tone = "plain",
}: {
  icon: any;
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
  children?: React.ReactNode;
  tone?: "plain" | "muted";
}) {
  return (
    <section
      className={cn(
        "rounded-3xl border p-5 space-y-4",
        tone === "muted"
          ? "border-slate-800/70 bg-[#0e0e12]/40"
          : "border-slate-800 bg-[#0e0e12]/60"
      )}
    >
      <header className="flex items-center gap-3">
        <div className="h-9 w-9 rounded-xl bg-primary/10 grid place-items-center shrink-0">
          <Icon className="h-4 w-4 text-primary" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-bold text-white">{title}</h3>
          {subtitle && (
            <p className="text-[11px] text-slate-500 mt-0.5">{subtitle}</p>
          )}
        </div>
        {right}
      </header>
      {children}
    </section>
  );
}

/* ── the tab ───────────────────────────────────────────────────────── */

export function PremiumAdmin() {
  const [rows, setRows] = useState<KeyRow[]>([]);
  const [role, setRole] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [setup, setSetup] = useState({ pepper: true, token: true, url: true });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [sortBy, setSortBy] = useState<SortBy>("created");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<string | null>(null);

  const [showMint, setShowMint] = useState(false);
  const [days, setDays] = useState("30");
  const [count, setCount] = useState("1");
  const [recipient, setRecipient] = useState("");
  const [note, setNote] = useState("");
  const [fresh, setFresh] = useState<string[]>([]);

  const load = useCallback(async () => {
    try {
      const res = await api.listPremiumKeys(500);
      setRows(res?.keys || []);
      setRole(res?.role || null);
      setStats(res?.stats || null);
      setSetup({
        pepper: Boolean(res?.pepper_set),
        token: Boolean(res?.partner_token_set),
        url: Boolean(res?.template_url_set),
      });
      // A key that vanished must not stay selected, or a bulk action
      // would try to touch a row that is no longer there.
      setSelected((old) => {
        const alive = new Set((res?.keys || []).map((k: KeyRow) => k.key_hash));
        return new Set([...old].filter((h) => alive.has(h)));
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

  const now = Date.now();

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const list = rows.filter((row) => {
      if (filter !== "all" && stateOf(row, now) !== filter) return false;
      if (!needle) return true;
      return [row.redeemed_by, row.redeemed_name, row.note, row.key_hash]
        .filter(Boolean)
        .some((f) => String(f).toLowerCase().includes(needle));
    });

    const order: KeyState[] = ["active", "unclaimed", "expired", "revoked"];
    return [...list].sort((a, b) => {
      if (sortBy === "state") {
        return order.indexOf(stateOf(a, now)) - order.indexOf(stateOf(b, now));
      }
      if (sortBy === "expires") {
        // Never-expiring keys last: they are not "soonest".
        const av = a.expires_at ?? Number.MAX_SAFE_INTEGER;
        const bv = b.expires_at ?? Number.MAX_SAFE_INTEGER;
        return av - bv;
      }
      return (b.created_at ?? 0) - (a.created_at ?? 0);
    });
  }, [rows, filter, query, sortBy, now]);

  const allShownSelected =
    visible.length > 0 && visible.every((r) => selected.has(r.key_hash));

  const toggleAll = () => {
    setSelected((old) => {
      const next = new Set(old);
      if (allShownSelected) visible.forEach((r) => next.delete(r.key_hash));
      else visible.forEach((r) => next.add(r.key_hash));
      return next;
    });
  };

  const toggleOne = (hash: string) => {
    setSelected((old) => {
      const next = new Set(old);
      next.has(hash) ? next.delete(hash) : next.add(hash);
      return next;
    });
  };

  /* ── actions ─────────────────────────────────────────────────────── */

  const mint = async () => {
    const duration = Number(days);
    if (Number.isNaN(duration) || duration < 0 || duration > 3650) {
      toast.error("Laufzeit: 0 (unbegrenzt) bis 3650 Tage.");
      return;
    }
    const amount = Math.max(1, Math.min(25, Number(count) || 1));
    if (amount > 1 && recipient.trim()) {
      toast.error("Mehrere Keys lassen sich nicht an eine Person schicken.");
      return;
    }
    if (recipient.trim() && !/^\d{15,25}$/.test(recipient.trim())) {
      toast.error("Die Discord-ID besteht nur aus Ziffern.");
      return;
    }

    setBusy(true);
    try {
      const made: string[] = [];
      for (let i = 0; i < amount; i++) {
        const res = await api.createPremiumKey({
          days: duration,
          user_id: recipient.trim() || undefined,
          note: note.trim() || undefined,
        });
        made.push(res.key);
        if (res.delivery && !["sent", "none"].includes(res.delivery)) {
          toast.warning(res.result);
        } else if (res.delivery === "sent") {
          toast.success(res.result);
        }
      }
      setFresh(made);
      if (amount > 1) toast.success(`${amount} Keys erstellt.`);
      setRecipient("");
      setNote("");
      setCount("1");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Key konnte nicht erstellt werden.");
    } finally {
      setBusy(false);
    }
  };

  const runOne = async (
    hash: string,
    what: "revoke" | "unrevoke" | "delete"
  ) => {
    if (what === "delete" && !confirm("Diesen Key endgültig löschen?")) return;
    if (
      what === "revoke" &&
      !confirm("Sperren? Premium wird sofort entzogen, auch im Template-Bot.")
    ) {
      return;
    }
    setBusy(true);
    try {
      const res =
        what === "delete"
          ? await api.deletePremiumKey(hash)
          : await api.revokePremiumKey(hash, what === "unrevoke");
      toast.success(res?.result || "Erledigt.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const runBulk = async (what: "revoke" | "delete") => {
    const hashes = [...selected];
    if (hashes.length === 0) return;
    const word = what === "delete" ? "endgültig löschen" : "sperren";
    if (!confirm(`${hashes.length} Keys ${word}?`)) return;

    setBusy(true);
    let done = 0;
    let failed = 0;
    try {
      for (const hash of hashes) {
        try {
          if (what === "delete") await api.deletePremiumKey(hash);
          else await api.revokePremiumKey(hash, false);
          done++;
        } catch {
          // Keep going: one bad row must not strand the other forty.
          failed++;
        }
      }
      if (failed) toast.warning(`${done} erledigt, ${failed} fehlgeschlagen.`);
      else toast.success(`${done} Keys ${what === "delete" ? "gelöscht" : "gesperrt"}.`);
      setSelected(new Set());
      await load();
    } finally {
      setBusy(false);
    }
  };

  /** Everything currently shown, as CSV. Never the keys — only hashes. */
  const exportCsv = () => {
    const header = [
      "status", "besitzer_id", "besitzer_name", "laufzeit_tage",
      "erstellt", "eingeloest", "laeuft_ab", "notiz", "hash",
    ];
    const lines = visible.map((row) =>
      [
        STATES[stateOf(row, now)].label,
        row.redeemed_by ?? "",
        row.redeemed_name ?? "",
        row.duration === 0 ? "unbegrenzt" : row.duration,
        fmtDateTime(row.created_at),
        fmtDateTime(row.redeemed_at),
        row.expires_at ? fmtDateTime(row.expires_at) : "nie",
        row.note ?? "",
        row.key_hash,
      ]
        // Quotes doubled and the field wrapped: a note with a comma or a
        // quote in it would otherwise shift every later column.
        .map((cell) => `"${String(cell).replace(/"/g, '""')}"`)
        .join(",")
    );

    const blob = new Blob(["\uFEFF" + [header.join(","), ...lines].join("\n")], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `premium-keys-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    toast.success(`${visible.length} Zeilen exportiert.`);
  };

  /* ── render ──────────────────────────────────────────────────────── */

  const problems = [
    !setup.pepper && {
      code: "PREMIUM_KEY_PEPPER",
      text: "Ohne diesen Wert lassen sich keine Keys erstellen. Wird er " +
            "später gesetzt, verfallen alle vorher erstellten Keys.",
    },
    !setup.token && {
      code: "PREMIUM_PARTNER_TOKEN",
      text: "Der Template-Bot kann nicht nachfragen, wer Premium hat.",
    },
    !setup.url && {
      code: "TEMPLATE_BOT_URL",
      text: "Sperren und Freigeben wirken erst nach bis zu 5 Minuten " +
            "statt sofort.",
    },
  ].filter(Boolean) as { code: string; text: string }[];

  return (
    <div className="space-y-5">
      {/* Anything broken belongs at the top, not buried under the list. */}
      {problems.length > 0 && (
        <Reveal className="rounded-2xl border border-amber-500/30 bg-amber-500/[0.06] px-5 py-4">
          <p className="text-sm font-bold text-amber-300 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            Einrichtung unvollständig
          </p>
          <ul className="mt-2 space-y-1.5">
            {problems.map((p) => (
              <li key={p.code} className="text-[12px] text-slate-400">
                <code className="text-amber-200/90">{p.code}</code> fehlt
                &nbsp;&mdash;&nbsp;{p.text}
              </li>
            ))}
          </ul>
        </Reveal>
      )}

      <Reveal delay={60} className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat
          label="Aktive Lizenzen"
          value={stats?.active ?? 0}
          hint={`${stats?.lifetime ?? 0} davon unbegrenzt`}
          tone="text-emerald-300"
          active={filter === "active"}
          onClick={() => setFilter(filter === "active" ? "all" : "active")}
        />
        <Stat
          label="Nicht eingelöst"
          value={stats?.unclaimed ?? 0}
          hint="warten auf einen Käufer"
          tone="text-sky-300"
          active={filter === "unclaimed"}
          onClick={() => setFilter(filter === "unclaimed" ? "all" : "unclaimed")}
        />
        <Stat
          label="Läuft bald ab"
          value={stats?.expiring_soon ?? 0}
          hint="in den nächsten 7 Tagen"
          tone="text-amber-300"
          active={sortBy === "expires"}
          onClick={() => setSortBy(sortBy === "expires" ? "created" : "expires")}
        />
        <Stat
          label="Neu (30 Tage)"
          value={stats?.created_30d ?? 0}
          hint={`${stats?.total ?? 0} Keys insgesamt`}
          tone="text-slate-200"
        />
      </Reveal>

      <Reveal delay={120}>
      <Panel
        icon={ShieldCheck}
        title="Premium-Rolle"
        subtitle="Wird alle 10 Minuten mit den gültigen Lizenzen abgeglichen."
        tone="muted"
      >
        {!role?.configured ? (
          <p className="text-[12px] text-slate-500">
            Keine Rolle eingestellt. Unter <b>Bot Config &rarr; Premium Role</b>{" "}
            eine Rollen-ID eintragen.
          </p>
        ) : role?.ok ? (
          <p className="text-[12px] text-emerald-300 flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <span>
              <b>{role.name}</b> &mdash; {role.members ?? 0} Mitglieder
            </span>
          </p>
        ) : (
          <p className="text-[12px] text-amber-300 flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            {role?.problem}
          </p>
        )}
      </Panel>
      </Reveal>

      {/* Minting is occasional, so it stays folded away by default. */}
      <Reveal delay={180}>
      <Panel
        icon={Plus}
        title="Key erstellen"
        subtitle="Ersetzt den früheren /key-Befehl."
        right={
          <button
            onClick={() => setShowMint((v) => !v)}
            className="px-4 py-2 rounded-xl bg-primary text-[11px] font-black uppercase tracking-widest hover:brightness-110 transition-all"
          >
            {showMint ? "Schließen" : "Neuer Key"}
          </button>
        }
      >
        {showMint && (
          <div className="space-y-4 pt-1">
            <div className="grid sm:grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <label
                  htmlFor="pk-days"
                  className="text-[11px] font-black uppercase tracking-widest text-slate-400"
                >
                  Laufzeit (Tage)
                </label>
                <input
                  id="pk-days"
                  type="number"
                  min={0}
                  max={3650}
                  className={INPUT}
                  value={days}
                  onChange={(e) => setDays(e.target.value)}
                />
                <div className="flex flex-wrap gap-1.5">
                  {[
                    ["30", "30 T"],
                    ["90", "90 T"],
                    ["365", "1 Jahr"],
                    ["0", "∞"],
                  ].map(([value, label]) => (
                    <button
                      key={value}
                      onClick={() => setDays(value)}
                      className={cn(
                        "px-2.5 py-1 rounded-lg text-[11px] font-bold border transition-colors",
                        days === value
                          ? "bg-primary/15 border-primary/40 text-white"
                          : "bg-[#0e0e12] border-slate-800 text-slate-400 hover:border-slate-700"
                      )}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-1.5">
                <label
                  htmlFor="pk-count"
                  className="text-[11px] font-black uppercase tracking-widest text-slate-400"
                >
                  Anzahl
                </label>
                <input
                  id="pk-count"
                  type="number"
                  min={1}
                  max={25}
                  className={INPUT}
                  value={count}
                  onChange={(e) => setCount(e.target.value)}
                />
                <p className="text-[11px] text-slate-500">
                  Bis 25 auf einmal, z.B. für ein Gewinnspiel.
                </p>
              </div>

              <div className="space-y-1.5">
                <label
                  htmlFor="pk-user"
                  className="text-[11px] font-black uppercase tracking-widest text-slate-400"
                >
                  Discord-ID (optional)
                </label>
                <input
                  id="pk-user"
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
                htmlFor="pk-note"
                className="text-[11px] font-black uppercase tracking-widest text-slate-400"
              >
                Notiz (optional)
              </label>
              <input
                id="pk-note"
                className={INPUT}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="z.B. Bestellung #42"
              />
            </div>

            <button
              onClick={mint}
              disabled={busy || !setup.pepper}
              className="w-full py-2.5 rounded-xl bg-primary text-[11px] font-black uppercase tracking-widest hover:brightness-110 disabled:opacity-40 transition-all"
            >
              {busy ? "Wird erstellt …" : "Erstellen"}
            </button>
          </div>
        )}

        {/* Shown once. Keys are stored hashed — this is the only moment
            they can ever be read. */}
        {fresh.length > 0 && (
          <div className="rounded-2xl border border-amber-500/30 bg-amber-500/[0.06] p-4 space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-[12px] font-bold text-amber-200">
                {fresh.length === 1 ? "Neuer Key" : `${fresh.length} neue Keys`}
                {" "}&mdash; jetzt notieren
              </p>
              <button
                onClick={() => setFresh([])}
                className="p-1 rounded-lg text-slate-500 hover:text-white transition-colors"
                aria-label="Ausblenden"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            {fresh.map((k) => (
              <div key={k} className="flex items-center gap-2">
                <code className="flex-1 font-mono text-sm text-white tracking-widest bg-[#0e0e12] rounded-lg px-3 py-2 select-all">
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
            {fresh.length > 1 && (
              <button
                onClick={() => {
                  navigator.clipboard?.writeText(fresh.join("\n"));
                  toast.success("Alle kopiert.");
                }}
                className="text-[11px] font-bold text-amber-200 hover:text-white transition-colors"
              >
                Alle {fresh.length} kopieren
              </button>
            )}
            <p className="text-[11px] text-amber-300/80">
              Keys werden nur verschlüsselt gespeichert und lassen sich
              später nicht mehr anzeigen.
            </p>
          </div>
        )}
      </Panel>
      </Reveal>

      {/* The list is the tab. */}
      <Reveal delay={240}>
      <Panel
        icon={KeyRound}
        title="Alle Keys"
        subtitle={`${visible.length} von ${rows.length} angezeigt`}
        right={
          <div className="flex items-center gap-1">
            <button
              onClick={exportCsv}
              disabled={visible.length === 0}
              className="p-2 rounded-lg text-slate-500 hover:text-white hover:bg-white/[0.04] disabled:opacity-30 transition-colors"
              aria-label="Als CSV exportieren"
              title="Angezeigte Zeilen als CSV"
            >
              <Download className="h-4 w-4" />
            </button>
            <button
              onClick={load}
              className="p-2 rounded-lg text-slate-500 hover:text-white hover:bg-white/[0.04] transition-colors"
              aria-label="Neu laden"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
        }
      >
        <div className="flex flex-col lg:flex-row gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-600" />
            <input
              className={cn(INPUT, "pl-10")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Name, Discord-ID, Notiz oder Hash"
              aria-label="Keys durchsuchen"
            />
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            {(
              [
                ["all", "Alle"],
                ["active", "Aktiv"],
                ["unclaimed", "Offen"],
                ["expired", "Abgelaufen"],
                ["revoked", "Gesperrt"],
              ] as [Filter, string][]
            ).map(([id, label]) => (
              <button
                key={id}
                onClick={() => setFilter(id)}
                className={cn(
                  "px-3 py-2 rounded-lg text-[11px] font-bold border transition-colors",
                  filter === id
                    ? "bg-primary/15 border-primary/40 text-white"
                    : "bg-[#0e0e12] border-slate-800 text-slate-400 hover:border-slate-700"
                )}
              >
                {label}
              </button>
            ))}
            <button
              onClick={() =>
                setSortBy(
                  sortBy === "created"
                    ? "expires"
                    : sortBy === "expires"
                    ? "state"
                    : "created"
                )
              }
              className="px-3 py-2 rounded-lg text-[11px] font-bold border bg-[#0e0e12] border-slate-800 text-slate-400 hover:border-slate-700 transition-colors flex items-center gap-1.5"
              title="Sortierung wechseln"
            >
              <ArrowUpDown className="h-3.5 w-3.5" />
              {sortBy === "created"
                ? "Neueste"
                : sortBy === "expires"
                ? "Ablauf"
                : "Status"}
            </button>
          </div>
        </div>

        {/* Bulk bar appears only when something is picked. */}
        {selected.size > 0 && (
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-primary/30 bg-primary/[0.07] px-4 py-2.5">
            <span className="text-[12px] font-bold text-white">
              {selected.size} ausgewählt
            </span>
            <div className="flex-1" />
            <button
              onClick={() => runBulk("revoke")}
              disabled={busy}
              className="px-3 py-1.5 rounded-lg text-[11px] font-black uppercase tracking-widest bg-amber-500/10 border border-amber-500/25 text-amber-200 hover:bg-amber-500/20 disabled:opacity-40 transition-all"
            >
              Sperren
            </button>
            <button
              onClick={() => runBulk("delete")}
              disabled={busy}
              className="px-3 py-1.5 rounded-lg text-[11px] font-black uppercase tracking-widest bg-red-500/10 border border-red-500/25 text-red-200 hover:bg-red-500/20 disabled:opacity-40 transition-all"
            >
              Löschen
            </button>
            <button
              onClick={() => setSelected(new Set())}
              className="px-3 py-1.5 rounded-lg text-[11px] font-bold text-slate-400 hover:text-white transition-colors"
            >
              Auswahl aufheben
            </button>
          </div>
        )}

        {loading ? (
          <p className="text-[12px] text-slate-500">Wird geladen …</p>
        ) : visible.length === 0 ? (
          <p className="text-[12px] text-slate-500">
            {rows.length === 0
              ? "Noch keine Keys erstellt."
              : "Zu dieser Suche gibt es nichts."}
          </p>
        ) : (
          <div className="space-y-1.5">
            <label className="flex items-center gap-2.5 px-3 text-[11px] text-slate-500 cursor-pointer">
              <input
                type="checkbox"
                checked={allShownSelected}
                onChange={toggleAll}
                className="accent-primary h-3.5 w-3.5"
              />
              Alle {visible.length} angezeigten auswählen
            </label>

            {visible.map((row, index) => {
              const state = stateOf(row, now);
              const meta = STATES[state];
              const left = remaining(row.expires_at);
              const isOpen = expanded === row.key_hash;

              return (
                <Reveal
                  key={row.key_hash}
                  // Capped at ten rows' worth: with two hundred keys a
                  // per-row delay would take half a minute to finish.
                  delay={Math.min(index, 10) * 35}
                  className={cn(
                    "rounded-xl border bg-[#0e0e12] transition-colors",
                    selected.has(row.key_hash)
                      ? "border-primary/40"
                      : "border-slate-800"
                  )}
                >
                  <div className="flex items-center gap-3 px-3 py-2.5">
                    <input
                      type="checkbox"
                      checked={selected.has(row.key_hash)}
                      onChange={() => toggleOne(row.key_hash)}
                      className="accent-primary h-3.5 w-3.5 shrink-0"
                      aria-label={`Key von ${ownerLabel(row)} auswählen`}
                    />

                    <span
                      className={cn("h-2 w-2 rounded-full shrink-0", meta.dot)}
                      title={meta.label}
                    />

                    <div className="min-w-0 flex-1">
                      <p className="text-[12.5px] text-slate-200 truncate">
                        {ownerLabel(row)}
                      </p>
                      <p className="text-[11px] text-slate-500 truncate">
                        {meta.label}
                        {" · "}
                        {row.duration === 0
                          ? "unbegrenzt"
                          : `${row.duration} Tage`}
                        {state === "active" && left !== null
                          ? ` · noch ${left} ${left === 1 ? "Tag" : "Tage"}`
                          : ""}
                        {row.note ? ` · ${row.note}` : ""}
                      </p>
                    </div>

                    <div className="flex items-center gap-0.5 shrink-0">
                      <button
                        onClick={() =>
                          setExpanded(isOpen ? null : row.key_hash)
                        }
                        className="p-1.5 rounded-lg text-slate-600 hover:text-white hover:bg-white/[0.04] transition-colors"
                        aria-label="Details anzeigen"
                      >
                        <ChevronDown
                          className={cn(
                            "h-4 w-4 transition-transform",
                            isOpen && "rotate-180"
                          )}
                        />
                      </button>
                      <button
                        onClick={() =>
                          runOne(
                            row.key_hash,
                            row.revoked ? "unrevoke" : "revoke"
                          )
                        }
                        disabled={busy}
                        className={cn(
                          "p-1.5 rounded-lg transition-colors disabled:opacity-40",
                          row.revoked
                            ? "text-slate-600 hover:text-emerald-300 hover:bg-emerald-500/10"
                            : "text-slate-600 hover:text-amber-300 hover:bg-amber-500/10"
                        )}
                        aria-label={row.revoked ? "Sperre aufheben" : "Sperren"}
                        title={row.revoked ? "Sperre aufheben" : "Sperren"}
                      >
                        {row.revoked ? (
                          <Undo2 className="h-4 w-4" />
                        ) : (
                          <Ban className="h-4 w-4" />
                        )}
                      </button>
                      <button
                        onClick={() => runOne(row.key_hash, "delete")}
                        disabled={busy}
                        className="p-1.5 rounded-lg text-slate-600 hover:text-red-300 hover:bg-red-500/10 disabled:opacity-40 transition-colors"
                        aria-label="Endgültig löschen"
                        title="Endgültig löschen"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>

                  {/* Everything the API knows, without cluttering the row. */}
                  {isOpen && (
                    <Reveal className="border-t border-slate-800/70 px-3 py-3 grid sm:grid-cols-2 gap-x-6 gap-y-2">
                      {[
                        ["Status", meta.label],
                        ["Erstellt", fmtDateTime(row.created_at)],
                        [
                          "Erstellt von",
                          row.created_name || row.created_by || "—",
                        ],
                        ["Eingelöst", fmtDateTime(row.redeemed_at)],
                        [
                          "Läuft ab",
                          row.expires_at ? fmtDate(row.expires_at) : "nie",
                        ],
                        ["Produkt", row.product],
                        ["Notiz", row.note || "—"],
                      ].map(([label, value]) => (
                        <div key={label} className="flex gap-2 text-[11.5px]">
                          <span className="text-slate-500 w-28 shrink-0">
                            {label}
                          </span>
                          <span className="text-slate-300 break-words min-w-0">
                            {value}
                          </span>
                        </div>
                      ))}
                      <div className="sm:col-span-2 flex gap-2 text-[11.5px]">
                        <span className="text-slate-500 w-28 shrink-0">
                          Hash
                        </span>
                        <code className="text-slate-500 font-mono break-all min-w-0">
                          {row.key_hash}
                        </code>
                      </div>
                    </Reveal>
                  )}
                </Reveal>
              );
            })}
          </div>
        )}
      </Panel>
      </Reveal>
    </div>
  );
}
