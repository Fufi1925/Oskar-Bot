"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  KeyRound,
  Link2,
  LockKeyhole,
  Search,
  Server,
  ShieldCheck,
  Unlink,
  UserCheck,
  Users,
  X,
} from "lucide-react";
import { api } from "@/lib/api";

interface Role {
  id: string;
  name: string;
  colour: string;
}
interface Target {
  id: string;
  name: string;
  icon?: string | null;
  member_count: number;
  system_channel?: { id: string; name: string } | null;
  roles: Role[];
}
interface PullMember {
  id: string;
  name: string;
  username?: string | null;
  avatar?: string | null;
  verified_at?: string | null;
  pull_status: string;
  pulled_at?: string | null;
  left?: boolean;
}

const statusLabel: Record<string, string> = {
  joined: "Gepullt",
  join_failed: "Pull fehlgeschlagen",
  target_unavailable: "Ziel nicht erreichbar",
  scope_missing: "Nicht autorisiert",
  not_requested: "Nicht autorisiert",
  authorized_waiting: "Autorisiert · Ziel fehlte",
};

export function UserPullPanel({ guildId }: { guildId: string }) {
  const [targets, setTargets] = useState<Target[]>([]);
  const [members, setMembers] = useState<PullMember[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [target, setTarget] = useState<{ id: string; name: string } | null>(
    null,
  );
  const [owner, setOwner] = useState(true);
  const [loading, setLoading] = useState(true);
  const [setupOpen, setSetupOpen] = useState(false);
  const [codeOpen, setCodeOpen] = useState(false);
  const [selectedTarget, setSelectedTarget] = useState("");
  const [selectedRole, setSelectedRole] = useState("");
  const [code, setCode] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [targetData, memberData] = await Promise.all([
        api.getPullTargets(guildId),
        api.getPullMembers(guildId),
      ]);
      setTargets(targetData.targets || []);
      setMembers(memberData.members || []);
      if (targetData.active_challenge?.target_guild_id) {
        setSelectedTarget(String(targetData.active_challenge.target_guild_id));
        setNotice("Der Code wurde bereits gesendet. Es wurde keine zweite Discord-Nachricht erstellt.");
        setCodeOpen(true);
      }
      setEnabled(Boolean(memberData.pull_enabled));
      setTarget(memberData.target || null);
      setOwner(true);
    } catch (error: any) {
      if (error?.status === 403) setOwner(false);
      else
        setNotice(error?.message || "User Pull konnte nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    void load();
  }, [load]);
  const chosen = targets.find((item) => item.id === selectedTarget);
  const shown = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase("de");
    return members.filter(
      (member) =>
        !needle ||
        member.name.toLocaleLowerCase("de").includes(needle) ||
        member.id.includes(needle),
    );
  }, [members, search]);
  const pulled = members.filter(
    (member) => member.pull_status === "joined",
  ).length;
  const ready = enabled && Boolean(target);

  const sendCode = async () => {
    if (!selectedTarget) return;
    setBusy(true);
    setNotice("");
    try {
      const result = await api.createPullChallenge(
        guildId,
        selectedTarget,
        selectedRole,
      );
      if (result.target_guild_id)
        setSelectedTarget(String(result.target_guild_id));
      setNotice(
        result.status === "already_sent"
          ? "Der Code wurde bereits gesendet. Es wurde keine zweite Discord-Nachricht erstellt."
          : "Der vierstellige Code wurde in den Systemkanal gesendet.",
      );
      setSetupOpen(false);
      setCodeOpen(true);
    } catch (error: any) {
      setNotice(error?.message || "Code konnte nicht gesendet werden.");
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    if (!/^\d{4}$/.test(code)) return;
    setBusy(true);
    setNotice("");
    try {
      await api.confirmPullChallenge(guildId, selectedTarget, code);
      setNotice("User Pull ist jetzt für zukünftige Verifizierungen aktiv.");
      setCodeOpen(false);
      setCode("");
      await load();
    } catch (error: any) {
      setNotice(error?.message || "Der Code konnte nicht bestätigt werden.");
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setBusy(true);
    try {
      await api.disableUserPull(guildId);
      setNotice("User Pull wurde deaktiviert.");
      await load();
    } catch (error: any) {
      setNotice(error?.message || "Deaktivieren fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  if (!owner) return <OwnerLock />;

  return (
    <div className="space-y-6">
      {notice && (
        <div className="rounded-xl border border-blue-500/25 bg-blue-500/10 px-4 py-3 text-sm text-blue-100">
          {notice}
        </div>
      )}

      <section className="overflow-hidden rounded-2xl border border-white/10 bg-slate-950/55 shadow-2xl shadow-blue-950/10">
        <div className="grid gap-5 p-5 sm:p-7 lg:grid-cols-[1fr_auto] lg:items-center">
          <div>
            <div className="mb-3 flex items-center gap-2 text-xs font-black uppercase tracking-[0.18em] text-blue-400">
              <Link2 className="h-4 w-4" /> Sicherer OAuth2 Pull
            </div>
            <h3 className="text-xl font-bold text-white sm:text-2xl">
              {ready ? (
                <>
                  Neue Mitglieder werden zu{" "}
                  <span className="text-blue-400">{target?.name}</span>{" "}
                  verbunden
                </>
              ) : enabled ? (
                "guilds.join ist aktiv – Zielserver auswählen"
              ) : (
                "User Pull ist ausgeschaltet"
              )}
            </h3>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
              Nur zukünftige Nutzer, die beim Verifizieren ausdrücklich{" "}
              <b className="text-slate-200">guilds.join</b> erlauben, werden
              hinzugefügt. Keine vorhandenen Mitglieder und keine OAuth-Tokens
              werden gespeichert.
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row lg:flex-col">
            <button
              disabled={loading || busy || !targets.length}
              onClick={() => {
                setSetupOpen(true);
                setNotice("");
              }}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 font-semibold text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Server className="h-4 w-4" />{" "}
              {target ? "Ziel ändern" : "Zielserver einrichten"}
            </button>
            {enabled && (
              <button
                disabled={busy}
                onClick={disable}
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-white/10 px-5 text-sm font-semibold text-slate-300 hover:bg-white/5"
              >
                <Unlink className="h-4 w-4" /> Deaktivieren
              </button>
            )}
          </div>
        </div>
      </section>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat icon={Users} label="Verifiziert" value={members.length} />
        <Stat icon={UserCheck} label="Gepullt" value={pulled} />
        <Stat icon={ShieldCheck} label="Modus" value="Nur neue" />
        <Stat icon={KeyRound} label="Tokens gespeichert" value="0" />
      </div>

      <section className="rounded-2xl border border-white/10 bg-slate-950/55 p-4 sm:p-6">
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h3 className="text-lg font-bold text-white">Mitglieder</h3>
            <p className="text-sm text-slate-500">
              Notwendige Discord-Daten und Autorisierungsstatus
            </p>
          </div>
          <label className="flex min-h-11 items-center gap-2 rounded-xl border border-white/10 bg-black/20 px-3 sm:w-72">
            <Search className="h-4 w-4 text-slate-500" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Name oder Discord-ID"
              className="w-full bg-transparent text-sm text-white outline-none placeholder:text-slate-600"
            />
          </label>
        </div>
        {loading ? (
          <div className="py-16 text-center text-sm text-slate-500">
            Mitglieder werden geladen …
          </div>
        ) : shown.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/10 py-16 text-center text-sm text-slate-500">
            Noch keine passenden Verifizierungen.
          </div>
        ) : (
          <div className="divide-y divide-white/[0.06]">
            {shown.map((member) => (
              <MemberRow key={member.id} member={member} />
            ))}
          </div>
        )}
      </section>

      {setupOpen && (
        <Modal title="Zielserver verbinden" onClose={() => setSetupOpen(false)}>
          <div className="space-y-5">
            <p className="text-sm leading-6 text-slate-400">
              University Bot muss auf dem Zielserver sein. Der tatsächliche
              Inhaber muss bei beiden Servern identisch sein.
            </p>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-slate-200">
                Zielserver
              </span>
              <select
                value={selectedTarget}
                onChange={(e) => {
                  setSelectedTarget(e.target.value);
                  setSelectedRole("");
                }}
                className="min-h-12 w-full rounded-xl border border-white/10 bg-slate-900 px-3 text-white outline-none focus:border-blue-500"
              >
                <option value="">Server auswählen</option>
                {targets.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-slate-200">
                Besondere Zielrolle{" "}
                <span className="font-normal text-slate-500">(optional)</span>
              </span>
              <select
                disabled={!chosen}
                value={selectedRole}
                onChange={(e) => setSelectedRole(e.target.value)}
                className="min-h-12 w-full rounded-xl border border-white/10 bg-slate-900 px-3 text-white outline-none disabled:opacity-50"
              >
                <option value="">Keine zusätzliche Rolle</option>
                {chosen?.roles.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.name}
                  </option>
                ))}
              </select>
            </label>
            {chosen && (
              <div className="rounded-xl border border-blue-500/20 bg-blue-500/[0.07] p-3 text-sm text-blue-100">
                Bestätigung an #
                {chosen.system_channel?.name || "kein Systemkanal"}
              </div>
            )}
            <button
              onClick={sendCode}
              disabled={!selectedTarget || !chosen?.system_channel || busy}
              className="flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-blue-600 font-bold text-white hover:bg-blue-500 disabled:opacity-50"
            >
              Code senden <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </Modal>
      )}

      {codeOpen && (
        <Modal title="Pull bestätigen" onClose={() => setCodeOpen(false)}>
          <div className="space-y-5 text-center">
            <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-blue-500/10 text-blue-400">
              <KeyRound className="h-7 w-7" />
            </div>
            <div>
              <p className="font-semibold text-white">
                Code bereits an Discord gesendet
              </p>
              <p className="mt-1 text-sm leading-6 text-slate-400">
                Der vierstellige Code ist 10 Minuten gültig. Neu laden oder
                erneutes Öffnen sendet keine zweite Nachricht.
              </p>
            </div>
            <input
              autoFocus
              inputMode="numeric"
              maxLength={4}
              value={code}
              onChange={(e) =>
                setCode(e.target.value.replace(/\D/g, "").slice(0, 4))
              }
              placeholder="0000"
              className="h-16 w-full rounded-xl border border-white/10 bg-black/30 text-center font-mono text-3xl tracking-[0.6em] text-white outline-none focus:border-blue-500"
            />
            <button
              onClick={confirm}
              disabled={!/^\d{4}$/.test(code) || busy}
              className="flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-blue-600 font-bold text-white hover:bg-blue-500 disabled:opacity-50"
            >
              <CheckCircle2 className="h-5 w-5" /> Aktivieren
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
}: {
  icon: any;
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-4">
      <Icon className="mb-3 h-5 w-5 text-blue-400" />
      <div className="text-xl font-black text-white">{value}</div>
      <div className="mt-1 text-xs text-slate-500">{label}</div>
    </div>
  );
}
function MemberRow({ member }: { member: PullMember }) {
  const good = member.pull_status === "joined";
  return (
    <div className="grid gap-3 py-4 sm:grid-cols-[minmax(0,1fr)_170px_150px] sm:items-center">
      <div className="flex min-w-0 items-center gap-3">
        {member.avatar ? (
          <img
            src={member.avatar}
            alt=""
            className="h-11 w-11 shrink-0 rounded-full object-cover"
          />
        ) : (
          <div className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-blue-500/10 font-bold text-blue-300">
            {member.name.slice(0, 1).toUpperCase()}
          </div>
        )}
        <div className="min-w-0">
          <div className="truncate font-semibold text-white">{member.name}</div>
          <div className="truncate font-mono text-xs text-slate-500">
            {member.id}
          </div>
        </div>
      </div>
      <div>
        <div className="text-[11px] uppercase tracking-wider text-slate-600">
          Verifiziert
        </div>
        <div className="mt-1 text-sm text-slate-300">
          {member.verified_at
            ? new Date(member.verified_at).toLocaleDateString("de-DE")
            : "—"}
        </div>
      </div>
      <div
        className={`w-fit rounded-full border px-2.5 py-1 text-xs font-semibold ${good ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300" : "border-slate-500/20 bg-slate-500/10 text-slate-400"}`}
      >
        {statusLabel[member.pull_status] || member.pull_status}
      </div>
    </div>
  );
}
function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 z-[100] grid place-items-end bg-black/70 p-0 backdrop-blur-sm sm:place-items-center sm:p-5"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="max-h-[92vh] w-full overflow-y-auto rounded-t-3xl border border-white/10 bg-[#080f20] p-5 shadow-2xl sm:max-w-lg sm:rounded-3xl sm:p-7"
      >
        <div className="mb-6 flex items-center justify-between">
          <h3 className="text-xl font-bold text-white">{title}</h3>
          <button
            onClick={onClose}
            className="grid h-10 w-10 place-items-center rounded-xl text-slate-400 hover:bg-white/5 hover:text-white"
            aria-label="Schließen"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
function OwnerLock() {
  return (
    <div className="relative min-h-[520px] overflow-hidden rounded-2xl border border-blue-500/20 bg-[#071127]">
      <div
        aria-hidden
        className="absolute inset-0 grid grid-cols-2 gap-4 p-6 opacity-30 blur-md"
      >
        <div className="rounded-2xl bg-blue-500/10" />
        <div className="rounded-2xl bg-white/5" />
        <div className="col-span-2 rounded-2xl bg-white/5" />
      </div>
      <div className="relative z-10 grid min-h-[520px] place-items-center p-6 text-center">
        <div className="max-w-md rounded-3xl border border-blue-400/25 bg-blue-950/80 p-7 shadow-2xl shadow-blue-900/40 backdrop-blur-xl">
          <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-blue-500/15 text-blue-300">
            <LockKeyhole className="h-7 w-7" />
          </div>
          <h3 className="text-xl font-bold text-white">
            Inhaberzugriff erforderlich
          </h3>
          <p className="mt-3 text-sm leading-6 text-blue-100/70">
            User Pull kann ausschließlich vom tatsächlichen
            Discord-Serverinhaber eingesehen und verwaltet werden.
            Administrator- oder Dashboard-Rechte reichen nicht aus.
          </p>
        </div>
      </div>
    </div>
  );
}
