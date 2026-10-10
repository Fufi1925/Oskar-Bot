"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowLeft, ArrowUpRight, ChevronDown, Gem, Home, LifeBuoy, Search, X } from "lucide-react";
import { BRAND_LOGO } from "@/lib/brand";
import { guildModuleFromHref } from "@/lib/guild-modules";
import { ThemeToggle } from "@/components/theme-toggle";

type Destination = { name: string; href: string; icon: React.ElementType; highlight?: boolean; notification?: number; children?: Destination[] };
export type WorkspaceNavigationItem = Destination | { name: string; items: Destination[] };

export function WorkspaceNavigation({ items, guildId, guild, moduleStates, mobileOpen, onClose, userName, role, premium, supportInvite }: {
  items: WorkspaceNavigationItem[];
  guildId: string | null;
  guild: { name: string; icon: string | null } | null;
  moduleStates: Record<string, boolean>;
  mobileOpen: boolean;
  onClose: () => void;
  userName: string;
  role: string;
  premium: boolean;
  supportInvite: string;
}) {
  const pathname = usePathname();
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const panel = useRef<HTMLElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const base = guildId ? `/dashboard/guild/${guildId}` : "/dashboard";
  const active = (href: string) => pathname === href || href !== base && href !== "/dashboard" && pathname.startsWith(`${href}/`);
  const activeGroup = items.find(item => "items" in item && item.items.some(link => active(link.href)))?.name;

  useEffect(() => { if (activeGroup) setExpanded(current => ({ ...current, [activeGroup]: true })); }, [activeGroup]);
  useEffect(() => { setQuery(""); }, [guildId]);
  useEffect(() => {
    if (!mobileOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    search.current?.focus();
    const keys = (event: KeyboardEvent) => {
      if (event.key === "Escape") { onClose(); return; }
      if (event.key !== "Tab") return;
      const elements = Array.from(panel.current?.querySelectorAll<HTMLElement>('a[href], button:not(:disabled), input:not(:disabled)') || []).filter(element => element.getClientRects().length > 0);
      const first = elements[0], last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    const desktop = window.matchMedia("(min-width: 1024px)");
    const resized = () => { if (desktop.matches) onClose(); };
    desktop.addEventListener("change", resized);
    document.addEventListener("keydown", keys);
    return () => { document.body.style.overflow = overflow; document.removeEventListener("keydown", keys); desktop.removeEventListener("change", resized); previous?.focus(); };
  }, [mobileOpen, onClose]);

  const needle = query.trim().toLocaleLowerCase();
  const matches = (item: Destination) => !needle || `${item.name} ${item.href.split("/").pop()}`.toLocaleLowerCase().includes(needle) || item.children?.some(child => child.name.toLocaleLowerCase().includes(needle));
  const visible = items.flatMap<WorkspaceNavigationItem>(item => {
    if (!("items" in item)) return matches(item) && item.name !== "Zurück zur Serverliste" ? [item] : [];
    const links = item.items.filter(link => item.name.toLocaleLowerCase().includes(needle) || matches(link));
    return links.length ? [{ ...item, items: links }] : [];
  });
  const navLink = (item: Destination, child = false) => {
    const selected = active(item.href);
    const key = guildId ? guildModuleFromHref(item.href, guildId) : null;
    const state = key ? moduleStates[key] : undefined;
    return <Link key={item.href} href={item.href} onClick={onClose} className={`cloudtix-workspace-nav-link ${child ? "is-child" : ""}`} aria-current={selected ? "page" : undefined}>
      <item.icon size={16} /><span>{item.name}</span>
      {Number(item.notification || 0) > 0 ? <b className="cloudtix-workspace-notice">{item.notification}</b> : key ? <i className="cloudtix-workspace-module-dot" data-enabled={state === undefined ? "unknown" : String(state)} title={state === true ? "Aktiviert" : state === false ? "Deaktiviert" : "Status nicht verfügbar"} /> : item.highlight ? <Gem size={12} className="cloudtix-workspace-premium-mark" /> : selected ? <i className="cloudtix-workspace-active-dot" /> : null}
    </Link>;
  };

  return <>
    {mobileOpen && <div className="cloudtix-workspace-nav-scrim" onClick={onClose} aria-hidden="true" />}
    <aside ref={panel} id="cloudtix-workspace-navigation" className={`cloudtix-workspace-navigation ${mobileOpen ? "is-open" : ""}`} role={mobileOpen ? "dialog" : undefined} aria-modal={mobileOpen || undefined} aria-label="Dashboard-Navigation">
      <Link href="/dashboard" className="cloudtix-workspace-brand" onClick={onClose}><img src={BRAND_LOGO} alt="" width={38} height={38} /><span>CloudTIX<small>{guildId ? "SERVER WORKSPACE" : "DEIN WORKSPACE"}</small></span></Link>
      <button type="button" className="cloudtix-workspace-nav-close" onClick={onClose} aria-label="Navigation schließen"><X size={18} /></button>
      {guildId && <div className="cloudtix-workspace-server-switch"><Link href="/dashboard/guilds" onClick={onClose}><ArrowLeft size={13} />Server wechseln<ArrowUpRight size={12} /></Link><div>{guild?.icon ? <img src={guild.icon} alt="" width={34} height={34} /> : <b>{(guild?.name || "S").slice(0, 1).toUpperCase()}</b>}<span>{guild?.name || "Server wird geladen …"}<small>Serververwaltung</small></span></div></div>}
      <label className="cloudtix-workspace-nav-search"><Search size={15} /><input ref={search} value={query} onChange={event => setQuery(event.target.value)} placeholder="Bereich suchen …" aria-label="Dashboard-Bereiche durchsuchen" />{query && <button type="button" onClick={() => { setQuery(""); search.current?.focus(); }} aria-label="Suche löschen"><X size={14} /></button>}</label>
      <div className="cloudtix-workspace-nav-scroll"><p className="cloudtix-workspace-nav-caption">{guildId ? "SERVER & MODULE" : "DEIN DASHBOARD"}</p><nav aria-label="Dashboard-Bereiche">{visible.map((item, index) => {
        if (!("items" in item)) return navLink(item);
        const open = Boolean(needle) || expanded[item.name];
        const Icon = item.items[0].icon;
        const id = `workspace-nav-group-${index}`;
        return <div className="cloudtix-workspace-nav-group" key={item.name}><button type="button" aria-expanded={Boolean(open)} aria-controls={id} className="cloudtix-workspace-nav-group-title" onClick={() => setExpanded(current => ({ ...current, [item.name]: !open }))}><Icon size={15} /><span>{item.name}</span><small>{item.items.length}</small><ChevronDown size={13} className={open ? "is-open" : ""} /></button>{open && <div id={id} className="cloudtix-workspace-nav-items">{item.items.map(link => <React.Fragment key={link.href}>{navLink(link)}{(active(link.href) || needle) && link.children?.map(child => navLink(child, true))}</React.Fragment>)}</div>}</div>;
      })}{!visible.length && <p className="cloudtix-workspace-nav-empty">Kein passender Bereich gefunden.</p>}</nav></div>
      <footer className="cloudtix-workspace-nav-footer"><div className="cloudtix-workspace-account"><span><b className="font-medium" data-no-translate>{userName}</b><small>{role}{premium ? " · Premium" : ""}</small></span><Link href="/account" onClick={onClose} aria-label="Mein Konto öffnen"><ArrowUpRight size={16} /></Link></div><a href={supportInvite} target="_blank" rel="noopener noreferrer"><LifeBuoy size={14} />Support auf Discord<ArrowUpRight size={12} /></a><Link href="/" onClick={onClose}><Home size={14} />Zur Website</Link><div className="cloudtix-workspace-nav-theme"><ThemeToggle embedded /></div></footer>
    </aside>
  </>;
}
