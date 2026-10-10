"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ArrowLeft, ArrowUpRight, ChevronDown, ChevronLeft, ChevronRight, Gem, Home, LifeBuoy, Pin, Search, X } from "lucide-react";
import { toast } from "sonner";
import { BRAND_LOGO } from "@/lib/brand";
import { guildModuleFromHref } from "@/lib/guild-modules";
import { ThemeToggle } from "@/components/theme-toggle";

type Destination = { name: string; href: string; icon: React.ElementType; highlight?: boolean; notification?: number; children?: Destination[] };
export type WorkspaceNavigationItem = Destination | { name: string; items: Destination[] };

export function WorkspaceNavigation({ items, guildId, guild, moduleStates, mobileOpen, onClose, userName, userId, role, premium, supportInvite, collapsed, onCollapsedChange }: {
  items: WorkspaceNavigationItem[];
  guildId: string | null;
  guild: { name: string; icon: string | null } | null;
  moduleStates: Record<string, boolean>;
  mobileOpen: boolean;
  onClose: () => void;
  userName: string;
  userId: string;
  role: string;
  premium: boolean;
  supportInvite: string;
  collapsed: boolean;
  onCollapsedChange: (value: boolean) => void;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [favorites, setFavorites] = useState<string[]>([]);
  const panel = useRef<HTMLElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);
  const gesture = useRef({ href: "", count: 0, time: 0 });
  const pointer = useRef("mouse");
  const storageKey = `cloudtix.workspace.favorites.${userId}`;
  const collapseKey = `cloudtix.workspace.collapsed.${userId}`;
  const base = guildId ? `/dashboard/guild/${guildId}` : "/dashboard";
  const favoriteKey = (href: string) => guildId && (href === base || href.startsWith(`${base}/`)) ? `server:${href.slice(base.length) || "/"}` : `page:${href}`;
  const active = (href: string) => pathname === href || href !== base && href !== "/dashboard" && pathname.startsWith(`${href}/`);
  const activeGroup = items.find(item => "items" in item && item.items.some(link => active(link.href)))?.name;
  const cancelNavigation = () => { if (pending.current) clearTimeout(pending.current); pending.current = null; };

  useEffect(() => {
    const load = () => {
      try {
        const saved: unknown = JSON.parse(localStorage.getItem(storageKey) || "[]");
        setFavorites(Array.isArray(saved) ? saved.filter((value): value is string => typeof value === "string").slice(0, 100) : []);
        onCollapsedChange(localStorage.getItem(collapseKey) === "true");
      } catch { setFavorites([]); onCollapsedChange(false); }
    };
    load();
    const sync = (event: StorageEvent) => { if (event.key === storageKey || event.key === collapseKey || event.key === null) load(); };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, [storageKey, collapseKey, onCollapsedChange]);
  useEffect(() => { if (activeGroup) setExpanded(current => ({ ...current, [activeGroup]: true })); }, [activeGroup]);
  useEffect(() => { setQuery(""); }, [guildId]);
  useEffect(() => { gesture.current = { href: "", count: 0, time: 0 }; return cancelNavigation; }, [pathname, userId]);
  useEffect(() => {
    if (!mobileOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    search.current?.focus();
    const keys = (event: KeyboardEvent) => {
      if (event.key === "Escape") { cancelNavigation(); onClose(); return; }
      if (event.key !== "Tab") return;
      const elements = Array.from(panel.current?.querySelectorAll<HTMLElement>('a[href], button:not(:disabled), input:not(:disabled)') || []).filter(element => element.getClientRects().length > 0 && getComputedStyle(element).visibility !== "hidden");
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

  const toggleFavorite = (item: Destination) => {
    cancelNavigation();
    gesture.current = { href: "", count: 0, time: 0 };
    const key = favoriteKey(item.href);
    const pinned = favorites.includes(key);
    const next = pinned ? favorites.filter(value => value !== key) : [...favorites, key];
    setFavorites(next);
    if (!pinned) requestAnimationFrame(() => {
      const scroll = panel.current?.querySelector<HTMLElement>(".cloudtix-workspace-nav-scroll");
      if (scroll) scroll.scrollTop = 0;
    });
    try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* Still usable when browser storage is disabled. */ }
    toast.success(pinned ? `${item.name} aus Favoriten entfernt` : `${item.name} angepinnt`);
  };
  const visit = (event: React.MouseEvent<HTMLAnchorElement>, item: Destination) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (event.detail === 0) { cancelNavigation(); onClose(); return; }
    event.preventDefault();
    const touch = pointer.current === "touch";
    const wait = touch ? 450 : 500;
    const now = Date.now();
    const count = gesture.current.href === item.href && now - gesture.current.time < wait ? gesture.current.count + 1 : 1;
    cancelNavigation();
    gesture.current = { href: item.href, count, time: now };
    if (count >= (touch ? 3 : 2)) { toggleFavorite(item); return; }
    pending.current = setTimeout(() => { pending.current = null; gesture.current = { href: "", count: 0, time: 0 }; onClose(); router.push(item.href); }, wait);
  };
  const toggleCollapsed = () => {
    cancelNavigation();
    setQuery("");
    if (window.matchMedia("(max-width: 1023px)").matches) { cancelNavigation(); onClose(); return; }
    onCollapsedChange(!collapsed);
    try { localStorage.setItem(collapseKey, String(!collapsed)); } catch { /* Session preference remains available. */ }
  };
  const needle = query.trim().toLocaleLowerCase();
  const matches = (item: Destination) => !needle || `${item.name} ${item.href.split("/").pop()}`.toLocaleLowerCase().includes(needle) || item.children?.some(child => child.name.toLocaleLowerCase().includes(needle));
  const allLinks: Destination[] = [];
  const addLink = (item: Destination) => { if (item.name !== "Zurück zur Serverliste" && !allLinks.some(link => link.href === item.href)) allLinks.push(item); item.children?.forEach(addLink); };
  items.forEach(item => "items" in item ? item.items.forEach(addLink) : addLink(item));
  const pinned = favorites.flatMap(key => { const item = allLinks.find(link => favoriteKey(link.href) === key); return item && matches(item) ? [item] : []; });
  const isPinned = (item: Destination) => pinned.some(link => link.href === item.href);
  const visible = items.flatMap<WorkspaceNavigationItem>(item => {
    if (!("items" in item)) return matches(item) && !isPinned(item) && item.name !== "Zurück zur Serverliste" ? [item] : [];
    const links = item.items.filter(link => (!isPinned(link) || link.children?.some(child => !isPinned(child))) && (item.name.toLocaleLowerCase().includes(needle) || matches(link)));
    return links.length ? [{ ...item, items: links }] : [];
  });
  const navLink = (item: Destination, child = false, favorite = false) => {
    const selected = active(item.href);
    const key = guildId ? guildModuleFromHref(item.href, guildId) : null;
    const state = key ? moduleStates[key] : undefined;
    return <Link key={item.href} href={item.href} onPointerDown={event => { pointer.current = event.pointerType; }} onClick={event => visit(event, item)} onKeyDown={event => { if (event.altKey && event.key.toLowerCase() === "p") { event.preventDefault(); toggleFavorite(item); } }} title={`${item.name} · PC: Doppelklick · Handy: 3× tippen · Tastatur: Alt+P zum ${favorite ? "Lösen" : "Anheften"}`} aria-label={`${item.name}${favorite ? " (Favorit)" : ""}`} className={`cloudtix-workspace-nav-link ${child ? "is-child" : ""} ${favorite ? "is-favorite" : ""}`} aria-current={selected ? "page" : undefined}>
      <item.icon size={17} /><span>{item.name}</span>
      {Number(item.notification || 0) > 0 ? <b className="cloudtix-workspace-notice">{item.notification}</b> : favorite ? <Pin size={12} className="cloudtix-workspace-pin-mark" /> : key ? <i className="cloudtix-workspace-module-dot" data-enabled={state === undefined ? "unknown" : String(state)} title={state === true ? "Aktiviert" : state === false ? "Deaktiviert" : "Status nicht verfügbar"} /> : item.highlight ? <Gem size={12} className="cloudtix-workspace-premium-mark" /> : selected ? <i className="cloudtix-workspace-active-dot" /> : null}
    </Link>;
  };

  return <>
    {mobileOpen && <div className="cloudtix-workspace-nav-scrim" onClick={() => { cancelNavigation(); onClose(); }} aria-hidden="true" />}
    <aside ref={panel} id="cloudtix-workspace-navigation" className={`cloudtix-workspace-navigation ${mobileOpen ? "is-open" : ""} ${collapsed ? "is-collapsed" : ""}`} role={mobileOpen ? "dialog" : undefined} aria-modal={mobileOpen || undefined} aria-label="Dashboard-Navigation">
      <Link href="/dashboard" className="cloudtix-workspace-brand" onClick={onClose} title="CloudTIX Dashboard"><img src={BRAND_LOGO} alt="" width={38} height={38} /><span>CloudTIX<small>{guildId ? "SERVER WORKSPACE" : "DEIN WORKSPACE"}</small></span></Link>
      <button type="button" className="cloudtix-workspace-nav-close" onClick={() => { cancelNavigation(); onClose(); }} aria-label="Navigation schließen"><X size={18} /></button>
      {guildId && <div className="cloudtix-workspace-server-switch"><Link href="/dashboard/guilds" onClick={onClose} title="Server wechseln"><ArrowLeft size={13} /><span>Server wechseln</span><ArrowUpRight size={12} /></Link><div>{guild?.icon ? <img src={guild.icon} alt="" width={34} height={34} /> : <b>{(guild?.name || "S").slice(0, 1).toUpperCase()}</b>}<span data-no-translate>{guild?.name || "Server wird geladen …"}<small>Serververwaltung</small></span></div></div>}
      <label className="cloudtix-workspace-nav-search"><Search size={15} /><input ref={search} value={query} onChange={event => setQuery(event.target.value)} placeholder="Bereich suchen …" aria-label="Dashboard-Bereiche durchsuchen" />{query && <button type="button" onClick={() => { setQuery(""); search.current?.focus(); }} aria-label="Suche löschen"><X size={14} /></button>}</label>
      <div className="cloudtix-workspace-nav-scroll"><nav aria-label="Dashboard-Bereiche">
        {pinned.length > 0 && <section className="cloudtix-workspace-favorites" aria-label="Favoriten"><p className="cloudtix-workspace-nav-caption"><Pin size={10} />FAVORITEN</p>{pinned.map(item => navLink(item, false, true))}</section>}
        <p className="cloudtix-workspace-nav-caption">{guildId ? "SERVER & MODULE" : "DEIN DASHBOARD"}</p>
        <p className="cloudtix-workspace-pin-hint">Anheften: <span className="pin-desktop-hint">Doppelklick</span><span className="pin-mobile-hint">3× tippen</span></p>
        {visible.map((item, index) => {
          if (!("items" in item)) return navLink(item);
          const open = Boolean(needle) || expanded[item.name];
          const Icon = item.items[0].icon;
          const id = `workspace-nav-group-${index}`;
          return <div className={`cloudtix-workspace-nav-group ${open ? "is-expanded" : ""}`} key={item.name}><button type="button" aria-expanded={Boolean(open)} aria-controls={id} className="cloudtix-workspace-nav-group-title" onClick={() => setExpanded(current => ({ ...current, [item.name]: !open }))}><Icon size={15} /><span>{item.name}</span><small>{item.items.length}</small><ChevronDown size={13} className={open ? "is-open" : ""} /></button><div id={id} className="cloudtix-workspace-nav-items">{item.items.map(link => <React.Fragment key={link.href}>{!isPinned(link) && navLink(link)}{(active(link.href) || needle) && link.children?.filter(child => child.href !== link.href && !isPinned(child)).map(child => navLink(child, true))}</React.Fragment>)}</div></div>;
        })}{!visible.length && !pinned.length && <p className="cloudtix-workspace-nav-empty">Kein passender Bereich gefunden.</p>}
      </nav></div>
      <footer className="cloudtix-workspace-nav-footer"><div className="cloudtix-workspace-account"><span><b className="font-medium" data-no-translate>{userName}</b><small>{role}{premium ? " · Premium" : ""}</small></span><Link href="/account" onClick={onClose} aria-label="Mein Konto öffnen" title="Mein Konto"><ArrowUpRight size={16} /></Link></div><a href={supportInvite} target="_blank" rel="noopener noreferrer" aria-label="Support auf Discord" title="Support auf Discord"><LifeBuoy size={16} /><span>Support auf Discord</span><ArrowUpRight size={12} /></a><Link href="/" onClick={onClose} aria-label="Zur Website" title="Zur Website"><Home size={16} /><span>Zur Website</span></Link><div className="cloudtix-workspace-nav-bottom"><ThemeToggle embedded compact /><button type="button" className="cloudtix-workspace-collapse" onClick={toggleCollapsed} aria-label={collapsed ? "Sidebar ausklappen" : "Sidebar einklappen"} aria-expanded={!collapsed} title={collapsed ? "Sidebar ausklappen" : "Sidebar einklappen"}>{collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}</button></div></footer>
    </aside>
  </>;
}
