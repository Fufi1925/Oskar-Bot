"use client";

import React, { useEffect, useMemo, useState } from "react";
import { Badge, Plus, Trash2, Save, RefreshCcw } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";

type Rule = { role_id: string; prefix: string; suffix: string; enabled: boolean };

export default function NicknamePage({ params }: { params: { guildId: string } }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [roles, setRoles] = useState<any[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [selectedRole, setSelectedRole] = useState("");
  const [prefix, setPrefix] = useState("");
  const [suffix, setSuffix] = useState("");

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const [cfg, roleData] = await Promise.all([
          api.getNicknameRules(params.guildId),
          api.getRoles(params.guildId),
        ]);
        setRules(cfg.rules || []);
        setRoles(roleData || []);
      } catch (err: any) {
        toast.error(err.message || "Nickname-Regeln konnten nicht geladen werden.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [params.guildId]);

  const roleOptions = useMemo(() => roles.filter((r) => r.name !== "@everyone").map((r) => ({ value: String(r.id), label: r.name })), [roles]);
  const roleName = (id: string) => roles.find((r) => String(r.id) === String(id))?.name || id;

  const addRule = () => {
    if (!selectedRole) return toast.error("Bitte eine Rolle auswählen.");
    if (!prefix && !suffix) return toast.error("Bitte Prefix oder Suffix eintragen.");
    const next = rules.filter((r) => r.role_id !== selectedRole);
    setRules([...next, { role_id: selectedRole, prefix, suffix, enabled: true }]);
    setSelectedRole(""); setPrefix(""); setSuffix("");
  };

  const save = async () => {
    setSaving(true);
    const promise = api.updateNicknameRules(params.guildId, { rules });
    toast.promise(promise, {
      loading: "Nickname-Regeln werden gespeichert...",
      success: "Nickname-Regeln wurden gespeichert.",
      error: "Nickname-Regeln konnten nicht gespeichert werden.",
    });
    try { await promise; } finally { setSaving(false); }
  };

  if (loading) return <div className="min-h-[300px] flex items-center justify-center"><RefreshCcw className="h-8 w-8 animate-spin text-primary" /></div>;

  return (
    <div className="max-w-5xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2"><Badge className="h-6 w-6 text-primary" />Nickname</h2>
        <p className="text-slate-400 mt-1">Lege fest, was vor oder nach dem Namen stehen soll, wenn ein User eine bestimmte Rolle hat.</p>
      </div>

      <section className="bg-[#10233f] border border-slate-800 rounded-3xl p-8 space-y-6 shadow-xl">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Select value={selectedRole} onValueChange={setSelectedRole} options={roleOptions} placeholder="Rolle auswählen" />
          <Input value={prefix} onChange={(e) => setPrefix(e.target.value)} placeholder="Vor dem Namen, z.B. [VIP] " maxLength={16} />
          <Input value={suffix} onChange={(e) => setSuffix(e.target.value)} placeholder="Nach dem Namen, z.B. ✦" maxLength={16} />
        </div>
        <Button onClick={addRule} className="gap-2"><Plus className="h-4 w-4" />Regel hinzufügen</Button>
      </section>

      <section className="bg-[#10233f] border border-slate-800 rounded-3xl overflow-hidden shadow-xl">
        <div className="p-6 border-b border-slate-800"><h3 className="font-black text-white">Aktive Regeln</h3></div>
        <div className="divide-y divide-slate-800">
          {rules.length === 0 ? <p className="p-6 text-slate-500">Keine Nickname-Regeln konfiguriert.</p> : rules.map((rule) => (
            <div key={rule.role_id} className="p-5 grid grid-cols-1 md:grid-cols-5 gap-4 items-center">
              <div className="md:col-span-2"><p className="text-xs text-slate-500 uppercase font-bold">Rolle</p><p className="text-white font-bold">{roleName(rule.role_id)}</p></div>
              <Input value={rule.prefix} onChange={(e) => setRules(rules.map((r) => r.role_id === rule.role_id ? { ...r, prefix: e.target.value } : r))} placeholder="Prefix" maxLength={16} />
              <Input value={rule.suffix} onChange={(e) => setRules(rules.map((r) => r.role_id === rule.role_id ? { ...r, suffix: e.target.value } : r))} placeholder="Suffix" maxLength={16} />
              <div className="flex items-center justify-end gap-3">
                <Switch checked={rule.enabled} onCheckedChange={(checked) => setRules(rules.map((r) => r.role_id === rule.role_id ? { ...r, enabled: checked } : r))} />
                <Button variant="ghost" size="sm" onClick={() => setRules(rules.filter((r) => r.role_id !== rule.role_id))} className="text-blue-400 hover:bg-blue-500/10"><Trash2 className="h-4 w-4" /></Button>
              </div>
            </div>
          ))}
        </div>
      </section>

      <Button onClick={save} disabled={saving} className="w-full h-14 text-base font-bold gap-2">
        {saving ? <RefreshCcw className="h-5 w-5 animate-spin" /> : <Save className="h-5 w-5" />}
        Speichern
      </Button>
    </div>
  );
}
