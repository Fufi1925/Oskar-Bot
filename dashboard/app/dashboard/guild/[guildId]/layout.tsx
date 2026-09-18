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
import { redirect } from "next/navigation";

export const revalidate = 0; // Never cache any guild dashboard page

import { Button } from "@/components/ui/button";
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

  if (error || !guild) redirect("/dashboard");

  return (
    <div className="space-y-5">
      {/* Zurueck zur Serverliste. */}
      <Link
        href="/dashboard/guilds"
        className="group inline-flex items-center gap-2 text-[14px] text-slate-500 transition-colors hover:text-white"
      >
        <ArrowLeft className="h-4 w-4 transition-transform group-hover:-translate-x-0.5" />
        Alle Server
      </Link>

      <GuildHeader
        guild={guild}
        isOwner={String(guild.owner_id) === String(access.userId ?? "")}
      />

      {/*
        Die Reiterleiste ist weg.

        Sie listete dieselben 41 Einträge wie die Seitenleiste links --
        nachgezählt, beide Listen waren deckungsgleich. Sieben
        zugeklappte Gruppen über jeder Seite hießen: zwei Wege zum
        selben Ziel, doppelte Pflege bei jedem neuen Reiter, und auf
        dem Telefon ein halber Bildschirm voll Navigation, bevor der
        Inhalt anfängt.

        Die Suche darin ist nicht verloren: die globale Suche oben
        (⌘K) findet dieselben Seiten und dazu die Server.
      */}
      <div className="min-h-[400px]">{children}</div>
    </div>
  );
}
