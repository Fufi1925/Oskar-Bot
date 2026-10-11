"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ChevronDown,
  Command,
  Home,
  LayoutDashboard,
  Pin,
  Search,
  Server,
  Shield,
  X,
} from "lucide-react";
import { useSession } from "next-auth/react";
import { toast } from "sonner";
import { BRAND_LOGO } from "@/lib/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { ADMIN_TAB_DETAILS } from "./admin-tab-details";

type NavigationTab = { id: string; label: string; icon: React.ElementType };
type NavigationGroup = { name: string; icon: React.ElementType; ids: string[] };

export function AdminNavigation({
  tabs,
  groups,
  active,
  onOpen,
  role,
  loading = false,
}: {
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
  const { data: session } = useSession();
  const userId = (session?.user as { id?: string } | undefined)?.id;
  const storageKey = userId ? `cloudtix.admin.favorites.${userId}` : "";
  const [favorites, setFavorites] = useState<{ key: string; ids: string[] }>({
    key: "",
    ids: [],
  });
  const favoriteIds = favorites.key === storageKey ? favorites.ids : [];
  const pointer = useRef("mouse");
  const gesture = useRef({ id: "", count: 0, time: 0 });
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);
  const panel = useRef<HTMLElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const activeGroup = groups.find((group) => group.ids.includes(active))?.name;

  function cancelNavigation() {
    if (pending.current !== null) clearTimeout(pending.current);
    pending.current = null;
  }

  useEffect(() => {
    let ids: string[] = [];
    try {
      const saved: unknown = storageKey
        ? JSON.parse(localStorage.getItem(storageKey) || "[]")
        : [];
      if (Array.isArray(saved))
        ids = [
          ...new Set(
            saved.filter(
              (id): id is string =>
                typeof id === "string" && /^[a-z][a-z0-9-]{0,99}$/.test(id),
            ),
          ),
        ];
    } catch {
      /* Favorites remain usable if browser storage is unavailable. */
    }
    setFavorites({ key: storageKey, ids });
  }, [storageKey]);

  useEffect(
    () => () => {
      cancelNavigation();
      gesture.current = { id: "", count: 0, time: 0 };
    },
    [storageKey, query, mobileOpen, tabs],
  );

  useEffect(() => {
    if (activeGroup)
      setExpanded((current) => ({ ...current, [activeGroup]: true }));
  }, [activeGroup]);

  useEffect(() => {
    const toggle = () => setMobileOpen((current) => !current);
    window.addEventListener("cloudtix-admin-navigation-toggle", toggle);
    return () =>
      window.removeEventListener("cloudtix-admin-navigation-toggle", toggle);
  }, []);

  useEffect(() => {
    if (!mobileOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    search.current?.focus();
    const keys = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const elements = Array.from(
        panel.current?.querySelectorAll<HTMLElement>(
          "a[href], button:not(:disabled), input:not(:disabled)",
        ) || [],
      ).filter((element) => element.getClientRects().length > 0);
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    const desktop = window.matchMedia("(min-width: 1024px)");
    const resize = () => {
      if (desktop.matches) setMobileOpen(false);
    };
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
  const matches = (tab: NavigationTab) =>
    !needle ||
    `${tab.label} ${ADMIN_TAB_DETAILS[tab.id]?.description || ""}`
      .toLocaleLowerCase()
      .includes(needle);
  // Resolve favorites against the permission-filtered tabs only.
  const pinned = favoriteIds.flatMap((id) => {
    const tab = tabs.find((item) => item.id === id);
    return tab && matches(tab) ? [tab] : [];
  });
  const visible = groups
    .map((group) => ({
      ...group,
      tabs: group.ids
        .map((id) => tabs.find((tab) => tab.id === id))
        .filter((tab): tab is NavigationTab => Boolean(tab))
        .filter((tab) => !favoriteIds.includes(tab.id) && matches(tab)),
    }))
    .filter((group) => group.tabs.length);

  function toggleFavorite(tab: NavigationTab) {
    cancelNavigation();
    gesture.current = { id: "", count: 0, time: 0 };
    const wasPinned = favoriteIds.includes(tab.id);
    const ids = wasPinned
      ? favoriteIds.filter((id) => id !== tab.id)
      : [...favoriteIds, tab.id];
    setFavorites({ key: storageKey, ids });
    if (storageKey) {
      try {
        localStorage.setItem(storageKey, JSON.stringify(ids));
      } catch {
        /* Keep the preference for this session. */
      }
    }
    if (wasPinned) {
      const group = groups.find((item) => item.ids.includes(tab.id));
      if (group) setExpanded((current) => ({ ...current, [group.name]: true }));
    }
    requestAnimationFrame(() => {
      if (!wasPinned) {
        const scroll = panel.current?.querySelector<HTMLElement>(
          ".cloudtix-admin-nav-scroll",
        );
        if (scroll) scroll.scrollTop = 0;
      }
      panel.current
        ?.querySelector<HTMLButtonElement>(`[data-admin-tab="${tab.id}"]`)
        ?.focus({ preventScroll: true });
    });
    toast.success(
      wasPinned
        ? `${tab.label} aus Favoriten entfernt`
        : `${tab.label} angepinnt`,
    );
  }

  function visit(
    event: React.MouseEvent<HTMLButtonElement>,
    tab: NavigationTab,
  ) {
    cancelNavigation();
    if (event.detail === 0) {
      gesture.current = { id: "", count: 0, time: 0 };
      onOpen(tab.id);
      setMobileOpen(false);
      return;
    }
    const touch = pointer.current === "touch";
    const wait = touch ? 450 : 500;
    const now = Date.now();
    const count =
      gesture.current.id === tab.id && now - gesture.current.time < wait
        ? gesture.current.count + 1
        : 1;
    gesture.current = { id: tab.id, count, time: now };
    if (count >= (touch ? 3 : 2)) {
      toggleFavorite(tab);
      return;
    }
    pending.current = setTimeout(() => {
      pending.current = null;
      gesture.current = { id: "", count: 0, time: 0 };
      onOpen(tab.id);
      setMobileOpen(false);
    }, wait);
  }

  const navTab = (tab: NavigationTab, favorite = false) => (
    <button
      type="button"
      key={tab.id}
      data-admin-tab={tab.id}
      aria-current={active === tab.id ? "page" : undefined}
      aria-label={`${tab.label}${favorite ? " (Favorit)" : ""}`}
      title={`${tab.label} · PC: Doppelklick · Handy: 3× tippen · Tastatur: Alt+P zum ${favorite ? "Lösen" : "Anheften"}`}
      className={`cloudtix-admin-nav-item ${favorite ? "is-favorite" : ""}`}
      onPointerDown={(event) => {
        pointer.current = event.pointerType;
      }}
      onClick={(event) => visit(event, tab)}
      onKeyDown={(event) => {
        if (event.altKey && event.key.toLowerCase() === "p") {
          event.preventDefault();
          toggleFavorite(tab);
        }
      }}
    >
      <tab.icon size={15} />
      <span>{tab.label}</span>
      {favorite ? (
        <Pin size={12} aria-hidden="true" />
      ) : active === tab.id ? (
        <i aria-hidden="true" />
      ) : null}
    </button>
  );

  return (
    <>
      {mobileOpen && (
        <div
          className="cloudtix-admin-nav-scrim"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}
      <aside
        ref={panel}
        id="cloudtix-admin-navigation"
        className={`cloudtix-admin-navigation ${mobileOpen ? "is-open" : ""}`}
        role={mobileOpen ? "dialog" : undefined}
        aria-modal={mobileOpen || undefined}
        aria-label="Admin-Navigation"
      >
        <Link href="/dashboard/admin" className="cloudtix-admin-brand">
          <img src={BRAND_LOGO} alt="" width={38} height={38} />
          <span>
            CloudTIX<small>ADMIN WORKSPACE</small>
          </span>
          <Command size={15} />
        </Link>
        <button
          className="cloudtix-admin-nav-close"
          type="button"
          aria-label="Admin-Navigation schließen"
          onClick={() => setMobileOpen(false)}
        >
          <X size={19} />
        </button>
        <label className="cloudtix-admin-nav-search">
          <Search size={15} />
          <input
            ref={search}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Bereich suchen …"
            aria-label="Admin-Bereiche durchsuchen"
          />
          {query && (
            <button
              type="button"
              onClick={() => {
                setQuery("");
                search.current?.focus();
              }}
              aria-label="Suche löschen"
            >
              <X size={13} />
            </button>
          )}
        </label>
        <div className="cloudtix-admin-nav-scroll">
          {pinned.length > 0 && (
            <section
              className="cloudtix-admin-nav-favorites"
              aria-label="Favoriten"
            >
              <div className="cloudtix-admin-nav-caption">
                <span>
                  <Pin size={11} />
                  Favoriten
                </span>
                <span>{pinned.length}</span>
              </div>
              <nav aria-label="Angepinnte Admin-Bereiche">
                {pinned.map((tab) => navTab(tab, true))}
              </nav>
            </section>
          )}
          <div className="cloudtix-admin-nav-caption">
            <span>Arbeitsbereiche</span>
            <span>{tabs.length}</span>
          </div>
          <nav aria-label="Admin-Bereiche">
            {visible.map((group) => {
              const open = Boolean(needle) || expanded[group.name];
              const GroupIcon = group.icon;
              const groupId = `admin-group-${groups.findIndex((entry) => entry.name === group.name)}`;
              return (
                <div key={group.name} className="cloudtix-admin-nav-group">
                  <button
                    className="cloudtix-admin-nav-group-title"
                    type="button"
                    aria-expanded={Boolean(open)}
                    aria-controls={groupId}
                    onClick={() =>
                      setExpanded((current) => ({
                        ...current,
                        [group.name]: !open,
                      }))
                    }
                  >
                    <GroupIcon size={15} />
                    <span>{group.name}</span>
                    <ChevronDown size={13} className={open ? "is-open" : ""} />
                  </button>
                  {open && (
                    <div id={groupId} className="cloudtix-admin-nav-items">
                      {group.tabs.map((tab) => navTab(tab))}
                    </div>
                  )}
                </div>
              );
            })}
            {loading && (
              <p className="cloudtix-admin-nav-empty">
                Berechtigungen werden geprüft …
              </p>
            )}
            {!loading && !visible.length && !pinned.length && (
              <p className="cloudtix-admin-nav-empty">
                {needle
                  ? "Kein passender Bereich gefunden."
                  : "Keine verfügbaren Bereiche."}
              </p>
            )}
          </nav>
        </div>
        <div className="cloudtix-admin-nav-footer">
          <div className="cloudtix-admin-role">
            <Shield size={14} />
            <span>{role}</span>
          </div>
          <Link href="/dashboard">
            <LayoutDashboard size={15} />
            Mein Dashboard
          </Link>
          <Link href="/dashboard/guilds">
            <Server size={15} />
            Meine Server
          </Link>
          <Link href="/">
            <Home size={15} />
            Zur Website
          </Link>
          <div className="cloudtix-admin-nav-theme">
            <ThemeToggle embedded />
          </div>
        </div>
      </aside>
    </>
  );
}
