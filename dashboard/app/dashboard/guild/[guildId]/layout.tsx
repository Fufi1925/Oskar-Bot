import React from "react";
import Link from "next/link";
import { ChevronRight, Server } from "lucide-react";
import { api } from "@/lib/api";
import { verifyGuildAccess } from "@/lib/guild-auth";
import { redirect } from "next/navigation";
import { GuildHeader } from "@/components/dashboard/guild-header";
import { GuildModuleStatus } from "@/components/dashboard/guild-module-status";

export const revalidate = 0;

export default async function GuildLayout({ children, params }: { children: React.ReactNode; params: { guildId: string } }) {
  const guildId = params.guildId;
  const access = await verifyGuildAccess(guildId);
  if (!access.allowed) redirect("/dashboard");
  let guild;
  try { guild = await api.getGuildDetails(guildId); }
  catch (error) { console.error("Failed to fetch guild details:", error); }
  if (!guild) redirect("/dashboard");

  return <div className="space-y-6">
    <nav aria-label="Seitennavigation" className="flex min-w-0 items-center gap-2 text-[11px] text-slate-500"><Link href="/dashboard/guilds" className="inline-flex shrink-0 items-center gap-2 hover:text-white"><Server size={13} />Deine Server</Link><ChevronRight size={12} /><span className="truncate text-slate-300">{guild.name}</span></nav>
    <GuildHeader guild={guild} isOwner={String(guild.owner_id) === String(access.userId ?? "")} />
    <GuildModuleStatus guildId={guildId}>{children}</GuildModuleStatus>
  </div>;
}
