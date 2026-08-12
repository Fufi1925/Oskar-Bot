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
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";
import { redirect } from "next/navigation";
import { isAdmin, cn } from "@/lib/utils";
import { fetchTeamAccess } from "@/lib/guild-auth";
import { Shield, Users, Server, Activity, Database, Cpu, Globe, Lock, Settings } from "lucide-react";

import { AdminContent } from "@/components/dashboard/admin-content";

export default async function AdminPage() {
  const session = await getServerSession(authOptions);

  if (!session?.user?.id) {
    redirect("/dashboard");
  }

  // Bot owners always get in. Everyone else needs a dashboard team role —
  // that is how staff reach the admin panel without the owner account.
  if (!isAdmin(session.user.id)) {
    const access = await fetchTeamAccess(session.user.id);
    const hasRole = Boolean(access && (access.is_owner || access.roles.length > 0));
    if (!hasRole) {
      redirect("/dashboard");
    }
  }

  return <AdminContent />;
}


