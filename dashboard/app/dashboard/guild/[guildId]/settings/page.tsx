import React from "react";
import { Settings2 } from "lucide-react";
import { api } from "@/lib/api";
import { GuildSettingsForm } from "@/components/dashboard/guild-settings-form";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function GuildSettingsPage({ params }: { params: { guildId: string } }) {
  // Channels and roles feed the pickers, so nobody has to paste IDs.
  const [config, channels, roles] = await Promise.all([
    api.getPrefix(params.guildId).catch(() => ({ prefix: ">" })),
    api.getChannels(params.guildId).catch(() => []),
    api.getRoles(params.guildId).catch(() => []),
  ]);

  const textChannels = (channels as any[])
    .filter((c) => !c.type || c.type === "text" || c.type === "news")
    .map((c) => ({ id: String(c.id), name: c.name }));

  const assignableRoles = (roles as any[])
    .filter((r) => r.name !== "@everyone")
    .map((r) => ({ id: String(r.id), name: r.name }));

  return (
    <div className="max-w-5xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Settings2 className="h-6 w-6 text-primary" />
          Settings
        </h2>
        <p className="text-slate-400 mt-1">
          How the bot behaves on this server.
        </p>
      </div>

      <GuildSettingsForm
        guildId={params.guildId}
        prefix={config.prefix}
        channels={textChannels}
        roles={assignableRoles}
      />
    </div>
  );
}
