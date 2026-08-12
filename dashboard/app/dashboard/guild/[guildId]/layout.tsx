/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║                                                                  ║
 * ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
 * ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
 * ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
 * ║                                                                  ║
 * ║           © 2026 University Bot Devs — All Rights Reserved               ║
 * ║                                                                  ║
 * ║   discord  ──  https://discord.gg/F3TedBAVZT                      ║
 * ║   youtube  ──  https://youtube.com/@University BotDevs                   ║
 * ║   github   ──  https://github.com/University Bot                        ║
 * ║                                                                  ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

import React from "react";
import Image from "next/image";
import Link from "next/link";
import { 
  Users, 
  ShieldCheck, 
  Ticket, 
  BarChart4, 
  FileText, 
  Settings,
  Hash,
  Shield,
  Layers,
  ArrowLeft,
  ShieldAlert
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { verifyGuildAccess } from "@/lib/guild-auth";

export const revalidate = 0; // Never cache any guild dashboard page

import { Button } from "@/components/ui/button";
import { GuildTabs } from "@/components/guild-tabs";
import { GuildHeader } from "@/components/dashboard/guild-header";

interface GuildLayoutProps {
  children: React.ReactNode;
  params: { guildId: string };
}

export default async function GuildLayout({
  children,
  params,
}: GuildLayoutProps) {
  const guildId = params.guildId;
  let guild;
  let error = null;

  // Authorization gate: the visitor must actually be allowed to manage this
  // server. Without this check any signed-in user could open the dashboard of
  // an arbitrary guild id.
  const access = await verifyGuildAccess(guildId);

  if (!access.allowed) {
    error = access.reason;
  } else {
    try {
      guild = await api.getGuildDetails(guildId);
    } catch (err: any) {
      console.error("Failed to fetch guild details:", err);
      error = err.message || "Failed to load guild data.";
    }
  }

  if (error || !guild) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] border-2 border-dashed border-blue-500/20 rounded-3xl bg-blue-500/5 p-12 text-center">
        <ShieldAlert className="h-16 w-16 text-blue-500 mb-6 opacity-50" />
        <h2 className="text-2xl font-bold text-white">Access Denied</h2>
        <p className="text-slate-400 mt-2 max-w-md">{error || "This guild does not exist or you do not have permission to manage it."}</p>
        <Link href="/dashboard/guilds" className="mt-8">
          <Button variant="outline">Back to Servers</Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
      {/* Breadcrumb / Back button */}
      <Link href="/dashboard/guilds" className="inline-flex items-center gap-2 text-slate-500 hover:text-white transition-colors text-sm font-medium group">
        <ArrowLeft className="h-4 w-4 group-hover:-translate-x-1 transition-transform" />
        Back to all servers
      </Link>

      <GuildHeader
        guild={guild}
        isOwner={String(guild.owner_id) === String(access.userId ?? "")}
      />

      {/* Modern Tab Navigation */}
      <GuildTabs guildId={guildId} />

      {/* Tab Content */}
      <div className="min-h-[400px]">
        {children}
      </div>
    </div>
  );
}
