import React from "react";
import { UserPlus } from "lucide-react";
import { api } from "@/lib/api";
import { AutoRoleForm } from "@/components/dashboard/autorole-form";

export const revalidate = 0; // Never cache this page

export default async function AutoRolePage({ params }: { params: { guildId: string } }) {
  const [config, roles] = await Promise.all([
    api.getAutoRole(params.guildId),
    api.getRoles(params.guildId),
  ]);

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-24">
      <div>
        <h2 className="text-2xl font-black text-white flex items-center gap-2 tracking-tight">
          <UserPlus className="h-6 w-6 text-primary" />
          Auto-Rolle
        </h2>
        <p className="text-slate-400 mt-1 text-sm">
          Rollen, die jedes neue Mitglied beim Beitritt automatisch bekommt.
        </p>
      </div>

      <AutoRoleForm initialConfig={config} roles={roles} guildId={params.guildId} />
    </div>
  );
}
