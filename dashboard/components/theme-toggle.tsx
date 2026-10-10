"use client";

import React, { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Moon, Sun } from "lucide-react";

export type DashboardTheme = "light" | "dark";

function applyTheme(theme: DashboardTheme) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (meta) meta.content = theme === "light" ? "#f4f5f7" : "#0a0a0c";
}

/** Global, persistent light/dark switch. Dark is the default for new users. */
export function ThemeToggle({ embedded = false, compact = false }: { embedded?: boolean; compact?: boolean }) {
  const [theme, setTheme] = useState<DashboardTheme>("dark");
  const pathname = usePathname();

  useEffect(() => {
    const saved = window.localStorage.getItem("dashboard-theme");
    const selected: DashboardTheme = saved === "light" ? "light" : "dark";
    setTheme(selected);
    applyTheme(selected);
    const sync = (event: Event) => {
      const next = (event as CustomEvent<DashboardTheme>).detail;
      if (next === "light" || next === "dark") setTheme(next);
    };
    window.addEventListener("dashboard-theme-change", sync);
    return () => window.removeEventListener("dashboard-theme-change", sync);
  }, []);

  const choose = (next: DashboardTheme) => {
    setTheme(next);
    window.localStorage.setItem("dashboard-theme", next);
    applyTheme(next);
    window.dispatchEvent(new CustomEvent("dashboard-theme-change", { detail: next }));
  };

  // The homepage and login panel already include their own theme controls.
  if (!embedded && (pathname === "/" || pathname === "/auth/login" || pathname.startsWith("/dashboard") || pathname.startsWith("/Tickets/Transkript/"))) return null;

  if (compact) return <button type="button" className="theme-filter-reset cloudtix-workspace-theme-button" onClick={() => choose(theme === "dark" ? "light" : "dark")} aria-label={theme === "dark" ? "Helles Design aktivieren" : "Dunkles Design aktivieren"} title={theme === "dark" ? "Helles Design" : "Dunkles Design"}>{theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}</button>;

  return (
    <div
      className={`theme-filter-reset dashboard-theme-toggle flex items-center rounded-full border border-white/10 bg-[#151519]/95 p-1 shadow-2xl shadow-black/40 backdrop-blur-xl ${embedded ? "relative" : "fixed bottom-5 right-5 z-40"}`}
      role="group"
      aria-label="Farbschema"
    >
      <button
        type="button"
        onClick={() => choose("light")}
        aria-label="Helles Design"
        aria-pressed={theme === "light"}
        title="Hell"
        className={`grid h-8 w-8 place-items-center rounded-full transition-colors ${
          theme === "light" ? "bg-white text-black" : "text-slate-500 hover:text-slate-300"
        }`}
      >
        <Sun className="h-4 w-4" />
      </button>
      <button
        type="button"
        onClick={() => choose("dark")}
        aria-label="Dunkles Design"
        aria-pressed={theme === "dark"}
        title="Dunkel"
        className={`grid h-8 w-8 place-items-center rounded-full transition-colors ${
          theme === "dark" ? "bg-white text-black" : "text-slate-500 hover:text-slate-300"
        }`}
      >
        <Moon className="h-4 w-4" />
      </button>
    </div>
  );
}
