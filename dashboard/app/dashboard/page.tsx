/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║                                                                  ║
 * ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
 * ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
 * ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
 * ║                                                                  ║
 * ║           © 2026 University Bot Devs — All Rights Reserved               ║
 * ║                                                                  ║
 * ║   discord  ──  https://discord.gg/MG3rYnUZJV                      ║
 * ║   youtube  ──  https://youtube.com/@University BotDevs                   ║
 * ║   github   ──  https://github.com/University Bot                        ║
 * ║                                                                  ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

import React from "react";
import { 
  Users, 
  MessageSquare, 
  Zap, 
  Activity,
  Server as ServerIcon,
  ShieldAlert,
  Settings,
  LifeBuoy,
  FileText
} from "lucide-react";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  let botInfo;
  let botStatus: any = null;
  let error = null;

  try {
    botInfo = await api.getBotInfo();
    // Live status drives the module list below instead of fixed strings.
    try {
      botStatus = await api.getBotStatus();
    } catch {
      botStatus = null;
    }
  } catch (err: any) {
    console.error("Failed to fetch bot info:", err);
    error = err.message || "Failed to connect to the bot API.";
    // Fallback data for UI structure if API fails
    botInfo = {
      name: "University Bot Bot",
      guilds: 0,
      users: 0,
      commands: 0,
      latency: "0ms"
    };
  }

  const stats = [
    { name: "Total Guilds", value: botInfo.guilds.toLocaleString(), icon: ServerIcon },
    { name: "Total Users", value: botInfo.users.toLocaleString(), icon: Users },
    { name: "System Uptime", value: "99.9%", icon: Activity },
    { name: "API Latency", value: botInfo.latency, icon: Activity },
  ];

  return (
    <div className="space-y-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 px-2">
        <div>
          <h1 className="text-4xl md:text-5xl font-bold text-white font-outfit tracking-tight">System <span className="text-blue-500 italic">Core.</span></h1>
          <p className="text-slate-400 mt-3 font-medium flex items-center gap-2">
            Status and live metrics for <span className="text-blue-500 font-bold px-2 py-0.5 rounded-lg bg-blue-500/10 border border-blue-500/20">{botInfo.name}</span>
          </p>
        </div>
        
        {error && (
          <div className="flex items-center gap-2 px-5 py-2.5 glass-blue rounded-2xl text-blue-500 text-xs font-bold uppercase tracking-widest animate-pulse">
            <ShieldAlert className="h-4 w-4" />
            <span>{error}</span>
          </div>
        )}
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.name} className="group glass border-white/5 p-7 rounded-[32px] relative overflow-hidden hover:border-blue-500/30 transition-all duration-500 shadow-2xl">
              {/* Animated Glow Overlay */}
              <div className="absolute inset-0 bg-gradient-to-br from-blue-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
              
             <div className="flex items-center justify-between relative z-10">
                <div>
                  <p className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] mb-2">{stat.name}</p>
                  <p className="text-3xl font-bold text-white font-outfit tracking-tight">{stat.value}</p>
                </div>
                <div className="p-4 bg-blue-500/10 rounded-2xl border border-blue-500/20 group-hover:scale-110 group-hover:bg-blue-500/20 transition-all duration-500">
                  <stat.icon className="h-6 w-6 text-blue-500" />
                </div>
             </div>
             
             <div className="absolute bottom-0 left-12 right-12 h-[1px] bg-blue-500/50 blur-[1px] opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
          </div>
        ))}
      </div>

      {/* Featured Modules & Support */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 glass border-white/5 rounded-[40px] p-10 relative group overflow-hidden shadow-2xl">
          <div className="absolute inset-0 bg-gradient-to-br from-blue-500/[0.03] to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-700" />
          
          <div className="flex items-center justify-between mb-8 relative z-10">
            <h2 className="text-2xl font-bold text-white font-outfit tracking-tight">Quick Actions</h2>
            <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20">
               <Zap className="h-3 w-3 text-blue-500" />
               <span className="text-[10px] font-black text-blue-500 uppercase tracking-widest">Efficiency</span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 relative z-10">
            {[
              { title: "Manage Servers", desc: "View and configure your Discord guilds.", icon: ServerIcon, href: "/dashboard/guilds" },
              { title: "Global Settings", desc: "Adjust your personal dashboard preferences.", icon: Settings, href: "/dashboard" },
              { title: "Support Matrix", desc: "Get help from our neural support team.", icon: LifeBuoy, href: "#" },
              { title: "Documentation", desc: "Learn how to master the University Bot engine.", icon: FileText, href: "#" },
            ].map((item) => (
              <a key={item.title} href={item.href} className="flex items-center gap-5 p-4 rounded-2xl bg-white/[0.02] border border-white/[0.03] group/item hover:bg-white/[0.05] hover:border-blue-500/20 transition-all">
                <div className="h-12 w-12 rounded-2xl bg-blue-500/5 border border-blue-500/10 flex items-center justify-center group-hover/item:bg-blue-500/10 transition-colors">
                   <item.icon className="h-5 w-5 text-blue-500/60 group-hover/item:text-blue-500 transition-colors" />
                </div>
                <div>
                  <h4 className="text-sm font-bold text-white group-hover/item:text-blue-500 transition-colors">{item.title}</h4>
                  <p className="text-[10px] text-slate-500 font-medium uppercase tracking-wider">{item.desc}</p>
                </div>
              </a>
            ))}
          </div>
        </div>

        <div className="glass border-white/5 rounded-[40px] p-10 flex flex-col justify-between relative group shadow-2xl overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-bl from-blue-500/[0.05] to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-700" />
          
          <div className="relative z-10">
            <h2 className="text-2xl font-bold text-white mb-3 font-outfit">Module Status</h2>
            <p className="text-slate-500 text-sm mb-10 font-medium">Global operational health of University Bot core.</p>
            
            <div className="space-y-4">
              {[
                {
                  name: "Gateway",
                  status: botStatus
                    ? `${Math.round(botStatus.latency)}ms`
                    : error
                    ? "Offline"
                    : "Unknown",
                  ok: Boolean(botStatus && botStatus.latency < 500),
                },
                {
                  name: "Servers",
                  status: `${botInfo.guilds.toLocaleString()} connected`,
                  ok: botInfo.guilds > 0,
                },
                {
                  name: "Shards",
                  status: botStatus ? `${botStatus.shards ?? 1} running` : "Unknown",
                  ok: Boolean(botStatus),
                },
              ].map((service) => (
                <div key={service.name} className="flex items-center justify-between p-4 bg-white/[0.02] rounded-2xl border border-white/[0.05] hover:border-blue-500/20 transition-colors">
                  <span className="text-xs font-bold text-slate-300">{service.name}</span>
                  <div className="flex items-center gap-3">
                    <div className={`h-1.5 w-1.5 rounded-full ${service.ok ? "bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)]" : "bg-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.5)]"}`} />
                    <span className={`text-[9px] uppercase font-black tracking-widest ${service.ok ? "text-emerald-500" : "text-amber-500"}`}>{service.status}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
          
          <a
            href="/dashboard/admin#health"
            className="mt-12 w-full py-4 glass-blue hover:bg-blue-500/10 text-blue-500 rounded-[20px] text-[11px] font-black uppercase tracking-[0.2em] transition-all border border-blue-500/20 relative z-10 flex items-center justify-center"
          >
            System Diagnostics
          </a>
          {/* Abstract Design Element */}
          <div className="absolute -bottom-10 -right-10 h-32 w-32 bg-blue-500/10 blur-3xl rounded-full" />
        </div>
      </div>
    </div>
  );
}
