/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║                                                                  ║
 * ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
 * ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
 * ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
 * ║                                                                  ║
 * ║           © 2026 CloudTIX Devs — All Rights Reserved               ║
 * ║                                                                  ║
 * ║   discord  ──  https://discord.gg/F3TedBAVZT                      ║
 * ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
 * ║                                                                  ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

import React from "react";
import { cn } from "@/lib/utils";

interface PageHeaderProps {
  title: string;
  description?: string;
  children?: React.ReactNode;
  icon?: React.ElementType;
  className?: string;
}

export const PageHeader = ({ 
  title, 
  description, 
  children, 
  icon: Icon,
  className 
}: PageHeaderProps) => {
  return (
    <div className={cn("cloudtix-workspace-page-header flex flex-col md:flex-row md:items-center justify-between gap-6 mb-8", className)}>
      <div>
        <h1 className="text-3xl font-black text-white flex items-center gap-3 tracking-tight">
          {Icon && <span><Icon className="h-5 w-5 text-slate-300 shrink-0" /></span>}
          {title}
        </h1>
        {description && (
          <p className="text-slate-400 mt-1">
            {description}
          </p>
        )}
      </div>
      {children && (
        <div className="flex items-center gap-4">
          {children}
        </div>
      )}
    </div>
  );
};
