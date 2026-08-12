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

"use client";

import React, { useState } from "react";
import Link from "next/link";
import { SiteNav } from "@/components/site-nav";
import { 
  Bot, 
  ChevronLeft, 
  Search, 
  ShieldCheck, 
  Zap, 
  Activity, 
  Layers, 
  Sparkles,
  Search as SearchIcon,
  BookOpen,
  Menu,
  X
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const DOCS_NAV = [
  {
    title: "Getting Started",
    items: [
      { name: "Introduction", description: "Learn about the Neural Core." },
      { name: "Quick Start", description: "Deploy in 30 seconds." },
      { name: "Architecture", description: "Deep dive into our engine." }
    ]
  },
  {
    title: "Security Modules",
    items: [
      { name: "Anti-Nuke", description: "Absolute lockdown protocols." },
      { name: "Verification", description: "Captcha & Neural checks." },
      { name: "Automod", description: "Context-aware AI filtering." }
    ]
  },
  {
    title: "Management",
    items: [
      { name: "Join to Create", description: "Dynamic voice channels." },
      { name: "Leveling", description: "Cinematic rank generation." },
      { name: "Tickets", description: "Enterprise helpdesk." }
    ]
  }
];

export default function DocsPage() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("Introduction");

  return (
    <div className="min-h-screen bg-[#0a0a0c] text-slate-200 font-sans">
      {/* Background Decor */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-indigo-600/[0.05] blur-[150px] rounded-full" />
      </div>

      {/* Dieselbe Leiste wie auf der Startseite -- vorher stand hier
          eine eigene mit anderem Logo und englischem "Exit Docs". */}
      <SiteNav />

      {/* Die Suche der Dokumentation, jetzt unter der Leiste statt
          darin: in der gemeinsamen Leiste ist dafuer kein Platz. */}
      <div className="border-b border-slate-800 px-5 lg:px-8 py-3">
        <div className="mx-auto max-w-[1400px] flex items-center gap-3">
          <button
            type="button"
            className="lg:hidden p-2 text-slate-400"
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            aria-label="Inhaltsverzeichnis"
          >
            {isSidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          <div className="relative flex-1 max-w-md group">
            <SearchIcon className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500 group-focus-within:text-indigo-400 transition-colors" />
            <input
              type="text"
              placeholder="Dokumentation durchsuchen …"
              className="w-full rounded-xl border border-slate-800 bg-[#131318] py-2.5 pl-11 pr-4 text-[14px] text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-slate-700 transition-colors"
            />
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto flex">
        {/* Sidebar */}
        <aside className={cn(
          "fixed inset-y-0 left-0 z-40 w-80 bg-[#0a0a0c] border-r border-slate-800 pt-24 lg:pt-8 transition-transform lg:translate-x-0 lg:static lg:bg-transparent",
          isSidebarOpen ? "translate-x-0" : "-translate-x-full"
        )}>
          <div className="h-full p-8 overflow-y-auto no-scrollbar">
            {DOCS_NAV.map((section) => (
              <div key={section.title} className="mb-10">
                <h4 className="text-[10px] font-black uppercase tracking-[0.4em] text-slate-600 mb-6">{section.title}</h4>
                <div className="space-y-1">
                  {section.items.map((item) => (
                    <button
                      key={item.name}
                      onClick={() => {
                        setActiveTab(item.name);
                        setIsSidebarOpen(false);
                      }}
                      className={cn(
                        "w-full flex flex-col items-start gap-1 p-4 rounded-2xl transition-all text-left",
                        activeTab === item.name 
                          ? "bg-blue-500/10 border border-blue-500/20 shadow-[0_0_20px_rgba(59,130,246,0.05)]" 
                          : "hover:bg-white/[0.02] border border-transparent"
                      )}
                    >
                      <span className={cn("text-sm font-bold", activeTab === item.name ? "text-blue-500" : "text-slate-300")}>{item.name}</span>
                      <span className="text-[10px] text-slate-600 font-bold uppercase tracking-tight">{item.description}</span>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </aside>

        {/* Content */}
        <main className="flex-1 min-w-0 p-6 sm:p-8 lg:p-16 relative z-10 max-w-4xl">
           <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-500 text-[10px] font-black uppercase tracking-widest mb-8">
            <BookOpen className="h-3 w-3" />
            V2.4 Runtime Environment
          </div>

          <h1 className="text-[34px] sm:text-[44px] font-extrabold text-white tracking-tight mb-8">
            {activeTab}<span className="text-indigo-400">.</span>
          </h1>

          <div className="prose prose-invert max-w-none">
             <p className="text-lg text-slate-400 mb-12 leading-relaxed">
               Welcome to the {activeTab} section of the University Bot Engine documentation. Our engine is designed for communities that demand absolute performance and cinematic management tools.
             </p>

             <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="p-8 rounded-[32px] glass border-white/5 space-y-4">
                   <Zap className="h-6 w-6 text-blue-500" />
                   <h3 className="text-xl font-bold text-white font-outfit uppercase">Fast Dispatch</h3>
                   <p className="text-sm text-slate-500 font-bold uppercase tracking-tight">Commands are dispatched via our global edge network in under 12ms.</p>
                </div>
                <div className="p-8 rounded-[32px] glass border-white/5 space-y-4">
                   <ShieldCheck className="h-6 w-6 text-emerald-500" />
                   <h3 className="text-xl font-bold text-white font-outfit uppercase">Secure Node</h3>
                   <p className="text-sm text-slate-500 font-bold uppercase tracking-tight">Every module runs in a dedicated neural sandbox with AES-256 encryption.</p>
                </div>
             </div>

             <div className="p-8 rounded-[40px] bg-blue-500/[0.02] border border-blue-500/10 relative overflow-hidden">
                <div className="absolute top-0 right-0 p-8 opacity-10">
                   <Layers className="h-32 w-32 text-blue-500" />
                </div>
                <h2 className="text-2xl font-bold text-white font-outfit uppercase tracking-tight mb-4">Neural Architecture</h2>
                  <h3 className="text-white font-bold">Protocol Overview</h3>
                <p className="text-slate-500 font-bold leading-relaxed mb-8">
                  The University Bot Engine utilizes a decentralized event stream processing model. When a Discord event is received, it is instantly routed to the nearest edge cluster.
                </p>
                <div className="bg-black/40 p-6 rounded-2xl border border-white/5 font-mono text-sm text-blue-500 mb-8">
                  $ University Bot initialize --cluster-shard [neural_07] --mode enterprise
                </div>
             </div>
          </div>

          <div className="mt-20 pt-12 border-t border-white/5 flex items-center justify-between">
             <div>
                <p className="text-[10px] font-black uppercase text-slate-600 tracking-[0.4em] mb-2">Internal Ref</p>
                <p className="text-sm font-bold text-slate-400">DOC-ID: CX_7749_B</p>
             </div>
             <div className="flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
                <span className="text-[10px] font-black uppercase text-blue-500 tracking-[0.2em]">Live Stream Active</span>
             </div>
          </div>
        </main>
      </div>
    </div>
  );
}
