"use client";

import React, { useEffect, useState } from "react";
import {
  Check, KeyRound, Loader2, Plus, Trash2, UserRound, UsersRound,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { UserPicker } from "@/components/dashboard/user-picker";
import { RolePicker } from "@/components/dashboard/pickers";

interface RoleGrant {
  role_id: string;
  name: string;
  color: number;
  member_count: number;
  missing: boolean;
}
interface UserGrant {
  user_id: string;
  username: string;
  display_name: string | null;
  avatar: string | null;
  member: boolean;
}
export function GuildAccessPanel({ guildId }: { guildId: string }) {
  const [roles, setRoles] = useState<RoleGrant[]>([]);
  const [users, setUsers] = useState<UserGrant[]>([]);
  const [selectedRole, setSelectedRole] = useState("");
  const [selectedUser, setSelectedUser] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [denied, setDenied] = useState(false);

  const load = async () => {
    try {
      const access = await api.getGuildAccess(guildId);
      setRoles(access.roles || []);
      setUsers(access.users || []);
      setDenied(false);
    } catch (error: any) {
      if (error?.status === 403 || String(error?.message || "").includes("Only the server")) {
        setDenied(true);
      } else {
        toast.error(error?.message || "Dashboard-Zugänge konnten nicht geladen werden.");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [guildId]); // eslint-disable-line react-hooks/exhaustive-deps

  const addRole = async () => {
    if (!selectedRole) return toast.error("Wähle zuerst eine Rolle aus.");
    setBusy(true);
    try {
      await api.addGuildAccessRole(guildId, selectedRole);
      toast.success("Die Rolle hat jetzt Dashboard-Zugang.");
      setSelectedRole("");
      await load();
    } catch (error: any) {
      toast.error(error?.message || "Rolle konnte nicht hinzugefügt werden.");
    } finally { setBusy(false); }
  };

  const addUser = async () => {
    if (!selectedUser) return toast.error("Wähle zuerst ein Mitglied aus.");
    setBusy(true);
    try {
      await api.addGuildAccessUser(guildId, selectedUser);
      toast.success("Das Mitglied hat jetzt Dashboard-Zugang.");
      setSelectedUser("");
      await load();
    } catch (error: any) {
      toast.error(error?.message || "Mitglied konnte nicht hinzugefügt werden.");
    } finally { setBusy(false); }
  };

  const removeRole = async (id: string) => {
    setBusy(true);
    try {
      await api.removeGuildAccessRole(guildId, id);
      toast.success("Rollen-Zugang entfernt.");
      await load();
    } catch (error: any) { toast.error(error?.message || "Zugang konnte nicht entfernt werden."); }
    finally { setBusy(false); }
  };

  const removeUser = async (id: string) => {
    setBusy(true);
    try {
      await api.removeGuildAccessUser(guildId, id);
      toast.success("Direkten Zugang entfernt.");
      await load();
    } catch (error: any) { toast.error(error?.message || "Zugang konnte nicht entfernt werden."); }
    finally { setBusy(false); }
  };

  if (loading) return (
    <div className="min-h-[300px] flex items-center justify-center">
      <Loader2 className="h-7 w-7 text-primary animate-spin opacity-60" />
    </div>
  );

  if (denied) return (
    <div className="relative overflow-hidden rounded-3xl border border-blue-400/25 bg-[#10141d] min-h-[430px]">
      {/* A real preview of the page remains visible underneath, like the
          Premium lock. It cannot be clicked and contains no access data. */}
      <div aria-hidden="true" className="pointer-events-none select-none p-6 blur-[7px] opacity-35">
        <div className="mb-6 rounded-2xl border border-blue-400/20 bg-blue-400/[0.06] p-5">
          <div className="h-4 w-48 rounded bg-blue-300/30" />
          <div className="mt-3 h-3 w-3/4 rounded bg-slate-500/30" />
        </div>
        <div className="grid gap-5 md:grid-cols-2">
          {[0, 1].map((column) => (
            <div key={column} className="rounded-2xl border border-slate-700 bg-[#131318] p-5">
              <div className="h-4 w-36 rounded bg-slate-400/30" />
              <div className="mt-5 h-11 rounded-xl border border-slate-700 bg-black/30" />
              <div className="mt-4 space-y-3">
                {[0, 1, 2].map((row) => (
                  <div key={row} className="flex items-center gap-3 rounded-xl border border-slate-800 p-3">
                    <div className="h-8 w-8 rounded-lg bg-blue-400/20" />
                    <div className="h-3 flex-1 rounded bg-slate-500/30" />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="absolute inset-0 flex items-center justify-center bg-[#090b0f]/55 backdrop-blur-[2px] p-6">
        <div className="max-w-md text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border border-blue-400/35 bg-blue-500/15 shadow-xl shadow-blue-500/10">
            <KeyRound className="h-7 w-7 text-blue-300" />
          </div>
          <div className="mt-5 inline-flex rounded-full border border-blue-400/25 bg-blue-400/10 px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-blue-300">
            Nur Server-Inhaber
          </div>
          <h3 className="mt-4 text-xl font-black text-white">Dashboard Access ist geschützt</h3>
          <p className="mt-2 text-sm leading-relaxed text-blue-100/65">
            Ausschließlich der tatsächliche Discord-Server-Inhaber darf Nutzer
            und Rollen für dieses Dashboard freischalten oder entfernen.
          </p>
        </div>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="rounded-3xl border border-primary/20 bg-primary/[0.06] p-5 flex gap-4">
        <div className="h-11 w-11 rounded-2xl bg-primary/15 flex items-center justify-center shrink-0">
          <KeyRound className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h3 className="font-bold text-white">Zugang zu diesem Server-Dashboard</h3>
          <p className="mt-1 text-sm leading-relaxed text-slate-400">
            Freigaben gelten nur für diesen Server. Nutzer müssen weiterhin mit Discord
            angemeldet und Mitglied des Servers sein. Änderungen werden sofort geprüft.
          </p>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-3xl border border-slate-800 bg-[#131318] overflow-hidden">
          <header className="p-6 border-b border-slate-800">
            <div className="flex items-center gap-3">
              <UsersRound className="h-5 w-5 text-violet-400" />
              <div>
                <h3 className="font-bold text-white">Zugang über Rollen</h3>
                <p className="text-xs text-slate-500 mt-1">Alle Mitglieder einer Rolle freischalten.</p>
              </div>
            </div>
            <div className="mt-5 space-y-2">
              <RolePicker
                guildId={guildId}
                value={selectedRole}
                onChange={(id) => setSelectedRole(id || "")}
                placeholder="Rolle auswählen…"
                allowClear
                excludeManaged
                excludeIds={roles.map((role) => role.role_id)}
              />
              <p className="text-[11px] text-slate-600">
                Die Rollen stehen in derselben Reihenfolge wie auf Discord — höchste zuerst.
              </p>
              <button onClick={addRole} disabled={busy || !selectedRole} className="w-full h-11 rounded-xl bg-primary text-white font-semibold text-sm disabled:opacity-40 hover:brightness-110 flex items-center justify-center gap-2">
                <Plus className="h-4 w-4" /> Rolle freischalten
              </button>
            </div>
          </header>
          <div className="p-3">
            {roles.length === 0 ? (
              <p className="py-8 text-center text-sm text-slate-600">Noch keine Rolle freigeschaltet.</p>
            ) : roles.map((role) => (
              <div key={role.role_id} className="flex items-center gap-3 px-3 py-3 rounded-2xl hover:bg-white/[0.025]">
                <span className="h-3 w-3 rounded-full shrink-0" style={{ backgroundColor: role.color ? `#${role.color.toString(16).padStart(6,"0")}` : "#64748b" }} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-white truncate">{role.name}</p>
                  <p className="text-[11px] text-slate-500">{role.member_count} Mitglieder{role.missing ? " · Rolle gelöscht" : ""}</p>
                </div>
                <button onClick={() => removeRole(role.role_id)} disabled={busy} title="Zugang entfernen" className="p-2 rounded-lg text-slate-600 hover:text-red-400 hover:bg-red-400/10">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-3xl border border-slate-800 bg-[#131318] overflow-hidden">
          <header className="p-6 border-b border-slate-800">
            <div className="flex items-center gap-3 mb-5">
              <UserRound className="h-5 w-5 text-blue-400" />
              <div>
                <h3 className="font-bold text-white">Einzelne Nutzer</h3>
                <p className="text-xs text-slate-500 mt-1">Mit Namen suchen oder eine Discord-ID einfügen.</p>
              </div>
            </div>
            <UserPicker guildId={guildId} value={selectedUser} onChange={setSelectedUser} label="Mitglied suchen" placeholder="Name oder Discord-ID…" />
            <button onClick={addUser} disabled={busy || !selectedUser} className="mt-3 w-full h-11 rounded-xl bg-primary text-white font-semibold text-sm disabled:opacity-40 hover:brightness-110 flex items-center justify-center gap-2">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
              Zugang vergeben
            </button>
          </header>
          <div className="p-3">
            {users.length === 0 ? (
              <p className="py-8 text-center text-sm text-slate-600">Noch kein Nutzer direkt freigeschaltet.</p>
            ) : users.map((user) => (
              <div key={user.user_id} className="flex items-center gap-3 px-3 py-3 rounded-2xl hover:bg-white/[0.025]">
                {user.avatar ? <img src={user.avatar} alt="" className="h-9 w-9 rounded-xl" /> : <div className="h-9 w-9 rounded-xl bg-slate-800 flex items-center justify-center"><UserRound className="h-4 w-4 text-slate-500" /></div>}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-white truncate">{user.display_name || user.username}</p>
                  <p className="text-[11px] text-slate-500 font-mono truncate">{user.user_id}{!user.member ? " · nicht mehr auf dem Server" : ""}</p>
                </div>
                <button onClick={() => removeUser(user.user_id)} disabled={busy} title="Zugang entfernen" className="p-2 rounded-lg text-slate-600 hover:text-red-400 hover:bg-red-400/10">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
