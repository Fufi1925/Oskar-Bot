"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Check,
  ChevronDown,
  Eye,
  KeyRound,
  Link2,
  Loader2,
  LockKeyhole,
  MoreHorizontal,
  Search,
  Server,
  ShieldCheck,
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
interface PullJob {
  status: string;
  total: number;
  completed: number;
  succeeded: number;
  failed: number;
  target_guild_id: string;
}

const statusLabel: Record<string, string> = {
  joined: "Gepullt",
  authorized: "Abrufbar",
  scope_missing: "Nicht autorisiert",
  not_requested: "Nicht autorisiert",
  authorization_expired: "Erneut autorisieren",
  authorization_revoked: "Autorisierung entfernt",
  authorization_store_failed: "Autorisierung fehlgeschlagen",
  join_failed: "Pull fehlgeschlagen",
};
const isAuthorized = (member: PullMember) =>
  ["authorized", "joined"].includes(member.pull_status);

export function UserPullPanel({ guildId }: { guildId: string }) {
  const [targets, setTargets] = useState<Target[]>([]);
  const [members, setMembers] = useState<PullMember[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [owner, setOwner] = useState(true);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [detail, setDetail] = useState<PullMember | null>(null);
  const [menu, setMenu] = useState<string | null>(null);
  const [wizard, setWizard] = useState(0);
  const [selectedTarget, setSelectedTarget] = useState("");
  const [withRole, setWithRole] = useState<boolean | null>(null);
  const [selectedRole, setSelectedRole] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<PullJob | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [targetData, memberData, jobData] = await Promise.all([
        api.getPullTargets(guildId),
        api.getPullMembers(guildId),
        api.getPullJob(guildId),
      ]);
      setTargets(targetData.targets || []);
      setMembers(memberData.members || []);
      setEnabled(Boolean(memberData.pull_enabled));
      setJob(jobData.job || null);
      if (targetData.active_challenge?.target_guild_id) {
        setSelectedTarget(String(targetData.active_challenge.target_guild_id));
        setNotice(
          "Der Code-Kanal wurde bereits erstellt. Es wurde kein zweiter Kanal angelegt.",
        );
        setWizard(4);
      }
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
  useEffect(() => {
    if (job?.status !== "running") return;
    const timer = window.setInterval(async () => {
      try {
        const result = await api.getPullJob(guildId);
        setJob(result.job || null);
        if (result.job?.status === "completed") {
          window.clearInterval(timer);
          setNotice(
            `Pull abgeschlossen: ${result.job.succeeded} erfolgreich, ${result.job.failed} fehlgeschlagen.`,
          );
          const refreshed = await api.getPullMembers(guildId);
          setMembers(refreshed.members || []);
        }
      } catch {
        /* next poll */
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [guildId, job?.status]);

  const chosenTarget = targets.find((item) => item.id === selectedTarget);
  const authorized = members.filter(isAuthorized).length;
  const unauthorized = Math.max(0, members.length - authorized);
  const authorizedPercent = members.length
    ? Math.round((authorized / members.length) * 100)
    : 0;
  const shown = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase("de");
    return members.filter((member) => {
      const textMatch =
        !needle ||
        member.name.toLocaleLowerCase("de").includes(needle) ||
        member.id.includes(needle);
      const statusMatch =
        filter === "all" ||
        (filter === "authorized"
          ? isAuthorized(member)
          : !isAuthorized(member));
      return textMatch && statusMatch;
    });
  }, [members, search, filter]);

  const begin = () => {
    setSelectedTarget("");
    setSelectedRole("");
    setWithRole(null);
    setCode("");
    setNotice("");
    setWizard(1);
  };
  const sendCode = async () => {
    setBusy(true);
    setNotice("");
    try {
      const result = await api.createPullChallenge(
        guildId,
        selectedTarget,
        withRole ? selectedRole : undefined,
      );
      if (result.target_guild_id)
        setSelectedTarget(String(result.target_guild_id));
      setNotice(
        result.status === "already_sent"
          ? "Der temporäre Code-Kanal existiert bereits. Es wurde kein zweiter Kanal erstellt."
          : "Der private Code-Kanal wurde auf dem Zielserver erstellt und wird nach 10 Minuten gelöscht.",
      );
      setWizard(4);
    } catch (error: any) {
      setNotice(error?.message || "Code-Kanal konnte nicht erstellt werden.");
    } finally {
      setBusy(false);
    }
  };
  const confirm = async () => {
    if (!/^\d{4}$/.test(code)) return;
    setBusy(true);
    setNotice("");
    try {
      const result = await api.confirmPullChallenge(
        guildId,
        selectedTarget,
        code,
      );
      setJob({
        status: result.job_status || "running",
        total: result.total || authorized,
        completed: 0,
        succeeded: 0,
        failed: 0,
        target_guild_id: selectedTarget,
      });
      setNotice(
        `Code bestätigt. Pull all für ${result.total ?? authorized} abrufbare Mitglieder wurde gestartet.`,
      );
      setWizard(0);
      setCode("");
    } catch (error: any) {
      setNotice(error?.message || "Code konnte nicht bestätigt werden.");
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

      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h3 className="text-2xl font-black text-white">
            Verifizierte Mitglieder
          </h3>
          <p className="mt-1 text-sm text-slate-500">
            Mitgliederdaten für deinen Discord-Server anzeigen und verwalten.
          </p>
        </div>
        <button
          onClick={begin}
          disabled={!enabled || authorized === 0 || job?.status === "running"}
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 text-sm font-bold text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Link2 className="h-4 w-4" /> Pull all
        </button>
      </div>

      <section className="rounded-3xl border border-white/10 bg-[#120d10] p-6 sm:p-8">
        <div className="grid grid-cols-2 gap-5">
          <Metric
            color="bg-emerald-500"
            value={authorized}
            label="Abrufbare Mitglieder"
          />
          <Metric
            color="bg-red-500"
            value={unauthorized}
            label="Nicht autorisierte Mitglieder"
            align="right"
          />
        </div>
        <div className="mt-6 flex h-8 overflow-hidden rounded-full bg-red-500">
          <div
            className="bg-emerald-500 transition-all duration-500"
            style={{ width: `${authorizedPercent}%` }}
          />
        </div>
        <div className="mt-5 flex items-center justify-center gap-2 text-slate-400">
          <Users className="h-5 w-5" /> Gesamtmitglieder:{" "}
          <b className="text-white">{members.length}</b>
        </div>
        {!enabled && (
          <p className="mt-4 text-center text-xs text-amber-300">
            Aktiviere User Pull zuerst in den Verify-Einstellungen.
          </p>
        )}
      </section>

      {job && (
        <section className="rounded-2xl border border-blue-500/20 bg-blue-500/[0.07] p-5">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 font-bold text-blue-100">
              {job.status === "running" && (
                <Loader2 className="h-4 w-4 animate-spin" />
              )}{" "}
              Pull-all-Fortschritt
            </span>
            <span className="text-sm text-blue-200">
              {job.completed}/{job.total}
            </span>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-black/30">
            <div
              className="h-full bg-blue-500 transition-all"
              style={{
                width: `${job.total ? (job.completed / job.total) * 100 : 100}%`,
              }}
            />
          </div>
          <div className="mt-3 flex gap-5 text-xs text-slate-400">
            <span className="text-emerald-300">
              {job.succeeded} erfolgreich
            </span>
            <span className="text-red-300">{job.failed} fehlgeschlagen</span>
          </div>
        </section>
      )}

      <section className="rounded-3xl border border-white/10 bg-[#120d10] p-5 sm:p-7">
        <div className="grid gap-5 md:grid-cols-[1fr_230px]">
          <label>
            <span className="mb-2 block text-sm font-semibold text-white">
              Suchen
            </span>
            <div className="flex min-h-12 items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.04] px-4">
              <Search className="h-5 w-5 text-slate-500" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Mitglieder suchen …"
                className="w-full bg-transparent text-white outline-none placeholder:text-slate-600"
              />
            </div>
          </label>
          <label>
            <span className="mb-2 block text-sm font-semibold text-white">
              Status
            </span>
            <div className="relative">
              <select
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="min-h-12 w-full appearance-none rounded-2xl border border-white/10 bg-[#1c1919] px-4 text-white outline-none"
              >
                <option value="all">Alle</option>
                <option value="authorized">Abrufbar</option>
                <option value="unauthorized">Nicht autorisiert</option>
              </select>
              <ChevronDown className="pointer-events-none absolute right-4 top-4 h-4 w-4 text-slate-500" />
            </div>
          </label>
        </div>
      </section>

      <section>
        <h3 className="text-xl font-bold text-white">Mitgliederliste</h3>
        <p className="mb-4 text-sm text-slate-500">
          Alle Mitglieder, die deinen Suchkriterien entsprechen.
        </p>
        <div className="overflow-visible rounded-2xl border border-white/10 bg-[#0d0c0d]">
          <div className="hidden grid-cols-[minmax(0,1fr)_180px_160px_120px_52px] border-b border-white/10 px-5 py-4 text-xs font-bold text-slate-500 md:grid">
            <span>Benutzername</span>
            <span>Discord-ID</span>
            <span>Verifiziert</span>
            <span>Status</span>
            <span />
          </div>
          {loading ? (
            <div className="py-16 text-center text-slate-500">
              Mitglieder werden geladen …
            </div>
          ) : shown.length === 0 ? (
            <div className="py-16 text-center text-slate-500">
              Keine passenden Mitglieder.
            </div>
          ) : (
            shown.map((member) => (
              <div
                key={member.id}
                className="relative grid gap-3 border-b border-white/[0.06] px-4 py-4 last:border-0 md:grid-cols-[minmax(0,1fr)_180px_160px_120px_52px] md:items-center md:px-5"
              >
                <MemberIdentity member={member} />
                <span className="font-mono text-xs text-slate-500">
                  {member.id}
                </span>
                <span className="text-sm text-slate-400">
                  {member.verified_at
                    ? new Date(member.verified_at).toLocaleDateString("de-DE")
                    : "—"}
                </span>
                <Status member={member} />
                <button
                  onClick={() => setMenu(menu === member.id ? null : member.id)}
                  className="absolute right-4 top-4 grid h-9 w-9 place-items-center rounded-full bg-white/[0.06] text-slate-400 hover:text-white md:static"
                >
                  <MoreHorizontal className="h-4 w-4" />
                </button>
                {menu === member.id && (
                  <div className="absolute right-4 top-14 z-20 w-40 rounded-xl border border-white/10 bg-[#191516] p-2 shadow-2xl">
                    <button
                      onClick={() => {
                        setDetail(member);
                        setMenu(null);
                      }}
                      className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-200 hover:bg-white/5"
                    >
                      <Eye className="h-4 w-4" /> Ansehen
                    </button>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </section>

      {detail && (
        <Modal title="Mitgliederinformationen" onClose={() => setDetail(null)}>
          <div className="space-y-5">
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
              <MemberIdentity member={detail} large />
            </div>
            <Info label="Discord-ID" value={detail.id} mono />
            <Info label="Anzeigename" value={detail.name} />
            <Info
              label="Verifiziert am"
              value={
                detail.verified_at
                  ? new Date(detail.verified_at).toLocaleString("de-DE")
                  : "—"
              }
            />
            <Info
              label="Pull-/Autorisierungsstatus"
              value={statusLabel[detail.pull_status] || detail.pull_status}
            />
          </div>
        </Modal>
      )}

      {wizard > 0 && (
        <Wizard
          title={
            wizard === 1
              ? "Zielserver auswählen"
              : wizard === 2
                ? "Zielrolle festlegen"
                : wizard === 3
                  ? "Pull all bestätigen"
                  : "Vierstelligen Code eingeben"
          }
          step={wizard}
          onClose={() => setWizard(0)}
        >
          {wizard === 1 && (
            <div className="space-y-5">
              <p className="text-sm leading-6 text-slate-400">
                Es erscheinen nur Server, auf die du Dashboard-Zugriff hast und
                auf denen University Bot installiert ist.
              </p>
              <Select
                value={selectedTarget}
                onChange={(value) => {
                  setSelectedTarget(value);
                  setSelectedRole("");
                }}
                placeholder="Server auswählen"
                options={targets.map((target) => ({
                  value: target.id,
                  label: target.name,
                }))}
              />
              <Next disabled={!selectedTarget} onClick={() => setWizard(2)} />
            </div>
          )}
          {wizard === 2 && (
            <div className="space-y-5">
              <p className="text-sm text-slate-400">
                Sollen alle gepullten Nutzer zusätzlich eine Rolle erhalten?
              </p>
              <div className="grid grid-cols-2 gap-3">
                <Choice
                  active={withRole === true}
                  onClick={() => setWithRole(true)}
                >
                  Ja
                </Choice>
                <Choice
                  active={withRole === false}
                  onClick={() => {
                    setWithRole(false);
                    setSelectedRole("");
                  }}
                >
                  Nein
                </Choice>
              </div>
              {withRole === true && (
                <Select
                  value={selectedRole}
                  onChange={setSelectedRole}
                  placeholder="Rolle auswählen"
                  options={(chosenTarget?.roles || []).map((role) => ({
                    value: role.id,
                    label: role.name,
                  }))}
                />
              )}
              <Next
                disabled={withRole === null || (withRole && !selectedRole)}
                onClick={() => setWizard(3)}
              />
            </div>
          )}
          {wizard === 3 && (
            <div className="space-y-5">
              <Summary label="Zielserver" value={chosenTarget?.name || "—"} />
              <Summary
                label="Zielrolle"
                value={
                  withRole
                    ? chosenTarget?.roles.find(
                        (role) => role.id === selectedRole,
                      )?.name || "—"
                    : "Keine zusätzliche Rolle"
                }
              />
              <Summary
                label="Abrufbare Mitglieder"
                value={String(authorized)}
              />
              <p className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-xs leading-5 text-amber-200">
                University Bot erstellt jetzt einen privaten Code-Kanal auf dem
                Zielserver. Er ist nur für Zielinhaber, dich und den Bot
                sichtbar und wird nach 10 Minuten gelöscht.
              </p>
              <button
                disabled={busy}
                onClick={sendCode}
                className="min-h-12 w-full rounded-xl bg-blue-600 font-bold text-white hover:bg-blue-500 disabled:opacity-50"
              >
                {busy ? "Kanal wird erstellt …" : "Pull starten"}
              </button>
            </div>
          )}
          {wizard === 4 && (
            <div className="space-y-5 text-center">
              <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-blue-500/10 text-blue-400">
                <KeyRound className="h-7 w-7" />
              </div>
              <p className="text-sm leading-6 text-slate-400">
                Gib den Code aus dem temporären Zielserver-Kanal ein. Code und
                Kanal sind 10 Minuten gültig.
              </p>
              <input
                autoFocus
                inputMode="numeric"
                maxLength={4}
                value={code}
                onChange={(e) =>
                  setCode(e.target.value.replace(/\D/g, "").slice(0, 4))
                }
                placeholder="0000"
                className="h-16 w-full rounded-xl border border-white/10 bg-black/30 text-center font-mono text-3xl tracking-[0.55em] text-white outline-none focus:border-blue-500"
              />
              <button
                disabled={!/^\d{4}$/.test(code) || busy}
                onClick={confirm}
                className="min-h-12 w-full rounded-xl bg-blue-600 font-bold text-white hover:bg-blue-500 disabled:opacity-50"
              >
                {busy ? "Wird geprüft …" : "Code bestätigen & Pull all starten"}
              </button>
            </div>
          )}
        </Wizard>
      )}
    </div>
  );
}

function Metric({
  color,
  value,
  label,
  align = "left",
}: {
  color: string;
  value: number;
  label: string;
  align?: "left" | "right";
}) {
  return (
    <div className={align === "right" ? "text-right" : ""}>
      <div
        className={`flex items-center gap-3 ${align === "right" ? "justify-end" : ""}`}
      >
        <span className={`h-3 w-3 rounded-full ${color}`} />
        <span className="text-3xl font-black text-white">{value}</span>
      </div>
      <p className="mt-1 text-sm text-slate-500">{label}</p>
    </div>
  );
}
function MemberIdentity({
  member,
  large = false,
}: {
  member: PullMember;
  large?: boolean;
}) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      {member.avatar ? (
        <img
          src={member.avatar}
          alt=""
          className={`${large ? "h-14 w-14" : "h-10 w-10"} shrink-0 rounded-full object-cover`}
        />
      ) : (
        <div
          className={`${large ? "h-14 w-14" : "h-10 w-10"} grid shrink-0 place-items-center rounded-full bg-blue-500/15 font-bold text-blue-300`}
        >
          {member.name.slice(0, 1).toUpperCase()}
        </div>
      )}
      <div className="min-w-0">
        <p className="truncate font-semibold text-white">{member.name}</p>
        {member.username && (
          <p className="truncate text-xs text-slate-500">@{member.username}</p>
        )}
      </div>
    </div>
  );
}
function Status({ member }: { member: PullMember }) {
  const good = isAuthorized(member);
  return (
    <span
      className={`w-fit rounded-full border px-2.5 py-1 text-xs font-semibold ${good ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300" : "border-red-500/20 bg-red-500/10 text-red-300"}`}
    >
      {statusLabel[member.pull_status] || member.pull_status}
    </span>
  );
}
function Info({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/20 p-4">
      <p className="text-xs uppercase tracking-wider text-slate-600">{label}</p>
      <p className={`mt-1 text-sm text-slate-200 ${mono ? "font-mono" : ""}`}>
        {value}
      </p>
    </div>
  );
}
function Summary({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <span className="text-sm text-slate-500">{label}</span>
      <b className="text-right text-sm text-white">{value}</b>
    </div>
  );
}
function Select({
  value,
  onChange,
  placeholder,
  options,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="min-h-12 w-full appearance-none rounded-xl border border-white/10 bg-slate-900 px-4 text-white outline-none focus:border-blue-500"
      >
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-4 top-4 h-4 w-4 text-slate-500" />
    </div>
  );
}
function Choice({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex min-h-12 items-center justify-center gap-2 rounded-xl border font-bold ${active ? "border-blue-500 bg-blue-500/15 text-blue-200" : "border-white/10 text-slate-400 hover:bg-white/5"}`}
    >
      {active && <Check className="h-4 w-4" />}
      {children}
    </button>
  );
}
function Next({
  disabled,
  onClick,
}: {
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      className="min-h-12 w-full rounded-xl bg-blue-600 font-bold text-white hover:bg-blue-500 disabled:opacity-40"
    >
      Weiter
    </button>
  );
}
function Wizard({
  title,
  step,
  onClose,
  children,
}: {
  title: string;
  step: number;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <Modal title={title} onClose={onClose}>
      <div className="mb-6 flex gap-2">
        {[1, 2, 3, 4].map((item) => (
          <div
            key={item}
            className={`h-1.5 flex-1 rounded-full ${item <= step ? "bg-blue-500" : "bg-white/10"}`}
          />
        ))}
      </div>
      {children}
    </Modal>
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
      className="fixed inset-0 z-[100] grid place-items-end bg-black/75 backdrop-blur-sm sm:place-items-center sm:p-5"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="max-h-[92vh] w-full overflow-y-auto rounded-t-3xl border border-white/10 bg-[#0d0b12] p-5 shadow-2xl sm:max-w-lg sm:rounded-3xl sm:p-7"
      >
        <div className="mb-6 flex items-center justify-between">
          <h3 className="text-xl font-bold text-white">{title}</h3>
          <button
            onClick={onClose}
            className="grid h-10 w-10 place-items-center rounded-xl text-slate-400 hover:bg-white/5 hover:text-white"
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
            Discord-Serverinhaber verwaltet werden.
          </p>
        </div>
      </div>
    </div>
  );
}
