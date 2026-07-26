"use client";

import React, { useEffect, useMemo, useState } from "react";
import { UserCheck, Plus, Trash2, Save, RefreshCcw, Shield } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";

export default function NoPrefixPage({ params }: { params: { guildId: string } }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [users, setUsers] = useState<string[]>([]);
  const [roles, setRoles] = useState<string[]>([]);
  const [allRoles, setAllRoles] = useState<any[]>([]);
  const [userInput, setUserInput] = useState("");
  const [selectedRole, setSelectedRole] = useState("");

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const [cfg, roleData] = await Promise.all([
          api.getNoPrefix(params.guildId),
          api.getRoles(params.guildId),
        ]);
        setUsers(cfg.users || []);
        setRoles(cfg.roles || []);
        setAllRoles(roleData || []);
      } catch (err: any) {
        toast.error(err.message || "No Prefix settings konnten nicht geladen werden.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [params.guildId]);

  const roleOptions = useMemo(() => {
    return allRoles
      .filter((role) => role.name !== "@everyone")
      .map((role) => ({ value: String(role.id), label: role.name }));
  }, [allRoles]);

  const addUser = () => {
    const id = userInput.trim();
    if (!/^\d{15,25}$/.test(id)) return toast.error("Bitte eine gültige Discord User-ID eintragen.");
    if (!users.includes(id)) setUsers([...users, id]);
    setUserInput("");
  };

  const addRole = () => {
    if (!selectedRole) return toast.error("Bitte eine Rolle auswählen.");
    if (!roles.includes(selectedRole)) setRoles([...roles, selectedRole]);
    setSelectedRole("");
  };

  const save = async () => {
    setSaving(true);
    const promise = api.updateNoPrefix(params.guildId, { users, roles, replace_users: true });
    toast.promise(promise, {
      loading: "No Prefix wird gespeichert...",
      success: "No Prefix wurde gespeichert.",
      error: "No Prefix konnte nicht gespeichert werden.",
    });
    try { await promise; } finally { setSaving(false); }
  };

  const roleName = (id: string) => allRoles.find((role) => String(role.id) === String(id))?.name || id;

  if (loading) return <div className="min-h-[300px] flex items-center justify-center"><RefreshCcw className="h-8 w-8 animate-spin text-primary" /></div>;

  return (
    <div className="max-w-5xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2"><UserCheck className="h-6 w-6 text-primary" />No Prefix</h2>
        <p className="text-slate-400 mt-1">User oder Rollen können den Bot ohne Prefix benutzen.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <section className="bg-[#10233f] border border-slate-800 rounded-3xl p-8 space-y-6 shadow-xl">
          <h3 className="text-lg font-black text-white flex items-center gap-2"><UserCheck className="h-5 w-5 text-primary" />User per ID</h3>
          <div className="flex gap-3">
            <Input value={userInput} onChange={(e) => setUserInput(e.target.value)} placeholder="Discord User-ID" />
            <Button onClick={addUser} className="gap-2"><Plus className="h-4 w-4" />Add</Button>
          </div>
          <div className="space-y-2">
            {users.length === 0 ? <p className="text-sm text-slate-500">Keine User eingetragen.</p> : users.map((id) => (
              <div key={id} className="flex items-center justify-between bg-slate-900/40 border border-slate-800 rounded-2xl px-4 py-3">
                <span className="font-mono text-sm text-slate-300">{id}</span>
                <Button variant="ghost" size="sm" onClick={() => setUsers(users.filter((x) => x !== id))} className="text-blue-400 hover:bg-blue-500/10"><Trash2 className="h-4 w-4" /></Button>
              </div>
            ))}
          </div>
        </section>

        <section className="bg-[#10233f] border border-slate-800 rounded-3xl p-8 space-y-6 shadow-xl">
          <h3 className="text-lg font-black text-white flex items-center gap-2"><Shield className="h-5 w-5 text-primary" />Rollen per Dropdown</h3>
          <div className="flex gap-3">
            <Select value={selectedRole} onValueChange={setSelectedRole} options={roleOptions} placeholder="Rolle auswählen" />
            <Button onClick={addRole} className="gap-2"><Plus className="h-4 w-4" />Add</Button>
          </div>
          <div className="space-y-2">
            {roles.length === 0 ? <p className="text-sm text-slate-500">Keine Rollen ausgewählt.</p> : roles.map((id) => (
              <div key={id} className="flex items-center justify-between bg-slate-900/40 border border-slate-800 rounded-2xl px-4 py-3">
                <span className="text-sm text-slate-300">{roleName(id)}</span>
                <Button variant="ghost" size="sm" onClick={() => setRoles(roles.filter((x) => x !== id))} className="text-blue-400 hover:bg-blue-500/10"><Trash2 className="h-4 w-4" /></Button>
              </div>
            ))}
          </div>
        </section>
      </div>

      <Button onClick={save} disabled={saving} className="w-full h-14 text-base font-bold gap-2">
        {saving ? <RefreshCcw className="h-5 w-5 animate-spin" /> : <Save className="h-5 w-5" />}
        Speichern
      </Button>
    </div>
  );
}
