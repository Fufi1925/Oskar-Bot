"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ChevronDown, Command, Home, LayoutDashboard, Search, Server, Shield, X } from "lucide-react";
import { BRAND_LOGO } from "@/lib/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { ADMIN_TAB_DETAILS } from "./admin-tab-details";

type NavigationTab = { id: string; label: string; icon: React.ElementType };
type NavigationGroup = { name: string; icon: React.ElementType; ids: string[] };

export function AdminNavigation({ tabs, groups, active, onOpen, role, loading = false }: {
  tabs: NavigationTab[];
  groups: NavigationGroup[];
  active: string;
  onOpen: (id: string) => void;
  role: string;
  loading?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const panel = useRef<HTMLElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const activeGroup = groups.find(group => group.ids.includes(active))?.name;

  useEffect(() => {
    if (activeGroup) setExpanded(current => ({ ...current, [activeGroup]: true }));
  }, [activeGroup]);

  useEffect(() => {
    const toggle = () => setMobileOpen(current => !current);
    window.addEventListener("cloudtix-admin-navigation-toggle", toggle);
    return () => window.removeEventListener("cloudtix-admin-navigation-toggle", toggle);
  }, []);

  useEffect(() => {
    if (!mobileOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    search.current?.focus();
    const keys = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setMobileOpen(false); return; }
      if (event.key !== "Tab") return;
      const elements = Array.from(panel.current?.querySelectorAll<HTMLElement>('a[href], button:not(:disabled), input:not(:disabled)') || []).filter(element => element.getClientRects().length > 0);
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    const desktop = window.matchMedia("(min-width: 1024px)");
    const resize = () => { if (desktop.matches) setMobileOpen(false); };
    desktop.addEventListener("change", resize);
    document.addEventListener("keydown", keys);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", keys);
      desktop.removeEventListener("change", resize);
      previous?.focus();
    };
  }, [mobileOpen]);

  const needle = query.trim().toLocaleLowerCase();
  const matches = (tab: NavigationTab) => !needle || `${tab.label} ${ADMIN_TAB_DETAILS[tab.id]?.description || ""}`.toLocaleLowerCase().includes(needle);
  const visible = groups.map(group => ({ ...group, tabs: group.ids.map(id => tabs.find(tab => tab.id === id)).filter((tab): tab is NavigationTab => Boolean(tab)).filter(matches) })).filter(group => group.tabs.length);

  return <>
    {mobileOpen && <div className="cloudtix-admin-nav-scrim" onClick={() => setMobileOpen(false)} aria-hidden="true" />}
    <aside ref={panel} id="cloudtix-admin-navigation" className={`cloudtix-admin-navigation ${mobileOpen ? "is-open" : ""}`} role={mobileOpen ? "dialog" : undefined} aria-modal={mobileOpen || undefined} aria-label="Admin-Navigation">
      <Link href="/dashboard/admin" className="cloudtix-admin-brand"><img src={BRAND_LOGO} alt="" width={38} height={38} /><span>CloudTIX<small>ADMIN WORKSPACE</small></span><Command size={15} /></Link>
      <button className="cloudtix-admin-nav-close" type="button" aria-label="Admin-Navigation schließen" onClick={() => setMobileOpen(false)}><X size={19} /></button>
      <label className="cloudtix-admin-nav-search"><Search size={15} /><input ref={search} value={query} onChange={event => setQuery(event.target.value)} placeholder="Bereich suchen …" aria-label="Admin-Bereiche durchsuchen" />{query && <button type="button" onClick={() => { setQuery(""); search.current?.focus(); }} aria-label="Suche löschen"><X size={13} /></button>}</label>
      <div className="cloudtix-admin-nav-scroll">
        <div className="cloudtix-admin-nav-caption"><span>Arbeitsbereiche</span><span>{tabs.length}</span></div>
        <nav aria-label="Admin-Bereiche">
          {visible.map(group => {
            const open = Boolean(needle) || expanded[group.name];
            const GroupIcon = group.icon;
            const groupId = `admin-group-${groups.findIndex(entry => entry.name === group.name)}`;
            return <div key={group.name} className="cloudtix-admin-nav-group">
              <button className="cloudtix-admin-nav-group-title" type="button" aria-expanded={Boolean(open)} aria-controls={groupId} onClick={() => setExpanded(current => ({ ...current, [group.name]: !open }))}><GroupIcon size={15} /><span>{group.name}</span><ChevronDown size={13} className={open ? "is-open" : ""} /></button>
              {open && <div id={groupId} className="cloudtix-admin-nav-items">{group.tabs.map(tab => <button type="button" key={tab.id} aria-current={active === tab.id ? "page" : undefined} className="cloudtix-admin-nav-item" onClick={() => { onOpen(tab.id); setMobileOpen(false); }}><tab.icon size={15} /><span>{tab.label}</span>{active === tab.id && <i aria-hidden="true" />}</button>)}</div>}
            </div>;
          })}
          {loading && <p className="cloudtix-admin-nav-empty">Berechtigungen werden geprüft …</p>}
          {!loading && !visible.length && <p className="cloudtix-admin-nav-empty">{needle ? "Kein passender Bereich gefunden." : "Keine verfügbaren Bereiche."}</p>}
        </nav>
      </div>
      <div className="cloudtix-admin-nav-footer"><div className="cloudtix-admin-role"><Shield size={14} /><span>{role}</span></div><Link href="/dashboard"><LayoutDashboard size={15} />Mein Dashboard</Link><Link href="/dashboard/guilds"><Server size={15} />Meine Server</Link><Link href="/"><Home size={15} />Zur Website</Link><div className="cloudtix-admin-nav-theme"><ThemeToggle embedded /></div></div>
    </aside>
  </>;
}
