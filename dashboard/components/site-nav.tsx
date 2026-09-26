"use client";

/**
 * Die obere Navigationsleiste der öffentlichen Seiten.
 *
 * Aufbau 1:1 nach der Vorlage: links der Markenname als reiner Text,
 * dann die Links mit zwei Aufklapp-Menüs, rechts der Sprachschalter
 * und der Kontoknopf. Höhe 76&nbsp;px, darunter eine einzelne Linie in
 * #1e1f22 — beides aus dem Screenshot gemessen, nicht geschätzt.
 *
 * **Warum eine eigene Komponente:** die Leiste stand vorher nur in
 * `app/page.tsx`. Jede weitere öffentliche Seite (Docs, Team, Status,
 * Impressum) hatte damit gar keine oder eine andere. Jetzt gibt es
 * eine, und sie sieht überall gleich aus.
 *
 * **Warum kein `useSession` für den Kontoknopf:** die Leiste steckt
 * auch auf Seiten, die ohne Anmeldung erreichbar sind. Ist niemand
 * angemeldet, zeigt der Knopf schlicht „Anmelden“ und startet den
 * Discord-Login — kein zweiter Zustand, den man übersehen kann.
 */

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { signIn, useSession } from "next-auth/react";
import {
  Activity, BookOpen, ChevronDown, ChevronRight, CircleHelp, CirclePlus,
  FileText, Globe, Grid2X2, Home, LayoutDashboard, LogIn, Shield,
  UserPlus, UserRound, Users, X,
} from "lucide-react";
import { LanguageSwitcher } from "@/components/language-switcher";
import { ThemeToggle } from "@/components/theme-toggle";
import { SUPPORT_INVITE } from "@/lib/legal";
import { cn } from "@/lib/utils";
import { normalisiereMarke } from "@/lib/brand";

const BRAND = normalisiereMarke(process.env.NEXT_PUBLIC_BRAND_NAME);

/** Die Einladung des Bots. Ohne Client-ID führt der Link ins Leere,
 *  deshalb fällt er dann auf den Support-Server zurück. */
const CLIENT_ID = process.env.NEXT_PUBLIC_DISCORD_CLIENT_ID || "";
export const INVITE_URL = CLIENT_ID
  ? `https://discord.com/oauth2/authorize?client_id=${CLIENT_ID}&permissions=8&scope=bot%20applications.commands`
  : SUPPORT_INVITE;

type Eintrag = { label: string; href: string; hint?: string };

const BEFEHLE: Eintrag[] = [
  { label: "Alle Befehle", href: "/commands", hint: "Durchsuchbar, mit Beschreibung" },
  { label: "Die wichtigsten", href: "/commands", hint: "Die 100 meistgenutzten zuerst" },
  { label: "Dokumentation", href: "/docs", hint: "Anleitungen und Einrichtung" },
];

/**
 * Die vier Rollen, fuer die man sich bewerben kann.
 *
 * Sie stehen hier UND im Bot (``web_apply_store.ROLES``). Ein Test
 * vergleicht beide Seiten: eine Rolle, die es hier gibt und dort
 * nicht, fuehrt zu einem Fragebogen, den der Bot ablehnt.
 */
const TEAM_ROLLEN: Eintrag[] = [
  { label: "Content Creator", href: "/team/apply?rolle=content", hint: "Videos, Clips und Beiträge" },
  { label: "Designer", href: "/team/apply?rolle=designer", hint: "Grafiken, Banner, Aussehen" },
  { label: "Moderator", href: "/team/apply?rolle=moderator", hint: "Support-Server betreuen" },
  { label: "Tester", href: "/team/apply?rolle=tester", hint: "Neues vor allen anderen testen" },
];

const UEBER: Eintrag[] = [
  { label: "Premium", href: "/premium", hint: "Preise und was enthalten ist" },
  { label: "Dokumentation", href: "/docs" },
  { label: "Status", href: "/status", hint: "Verfügbarkeit in Echtzeit" },
  { label: "Community Ideen", href: "/ideas", hint: "Vorschläge ansehen und bewerten" },
  { label: "Team", href: "/team" },
  { label: "Impressum", href: "/imprint" },
];

/**
 * Ein Aufklapp-Menü in der Leiste.
 *
 * `tone` faerbt die Beschriftung -- „Team beitreten“ ist in der
 * Vorlage der einzige gruene Punkt. `footer` haengt einen Link ans
 * Ende, damit man auch ohne Rollenwahl auf die Seite kommt.
 */
function Dropdown({
  label,
  items,
  tone,
  icon: Icon,
  footer,
}: {
  label: string;
  items: Eintrag[];
  tone?: "emerald";
  icon?: React.ComponentType<{ className?: string }>;
  footer?: { label: string; href: string };
}) {
  const [open, setOpen] = React.useState(false);
  const box = React.useRef<HTMLDivElement>(null);

  // Schliessen, sobald der Zeiger die Gruppe verlaesst. Ein Klick
  // daneben reicht hier nicht: das Menue oeffnet beim Ueberfahren,
  // und dann erwartet niemand, dass es stehen bleibt.
  React.useEffect(() => {
    if (!open) return;
    const weg = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", weg);
    return () => document.removeEventListener("mousedown", weg);
  }, [open]);

  return (
    <div
      ref={box}
      className="relative"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className={cn(
          "flex items-center gap-1.5 text-[15px] transition-colors py-2",
          tone === "emerald"
            ? "text-emerald-400 hover:text-emerald-300"
            : "text-slate-300 hover:text-white",
        )}
      >
        {Icon && <Icon className="h-4 w-4" />}
        {label}
        <ChevronDown
          className={cn(
            "h-4 w-4 transition-transform duration-200",
            tone === "emerald" ? "text-emerald-500/70" : "text-slate-500",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <div className="absolute left-0 top-full pt-2 z-50">
          <div className="w-64 rounded-2xl border border-slate-800 bg-[#131318] p-2 shadow-2xl shadow-black/60">
            {items.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className="block rounded-xl px-3 py-2.5 hover:bg-white/[0.04] transition-colors"
              >
                <span className="block text-[14px] text-slate-200">
                  {item.label}
                </span>
                {item.hint && (
                  <span className="block text-[12px] text-slate-500 mt-0.5">
                    {item.hint}
                  </span>
                )}
              </Link>
            ))}

            {footer && (
              <Link
                href={footer.href}
                onClick={() => setOpen(false)}
                className="mt-1 block border-t border-slate-800 px-3 pt-2.5 pb-1 text-[13px] text-slate-500 hover:text-white transition-colors"
              >
                {footer.label} &rarr;
              </Link>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

type MobileIcon = React.ComponentType<{ className?: string }>;

function MobileNavLink({ href, label, icon: Icon, onClick, external, active, primary, compact }: { href: string; label: string; icon: MobileIcon; onClick: () => void; external?: boolean; active?: boolean; primary?: boolean; compact?: boolean }) {
  const style = cn(
    "group flex w-full items-center border transition-all duration-200",
    compact ? "gap-2.5 rounded-2xl px-3 py-3 text-[13px]" : "gap-3 rounded-2xl px-4 py-3.5 text-[15px]",
    primary
      ? "border-blue-300/25 bg-gradient-to-r from-blue-600 to-indigo-500 text-white shadow-[0_14px_35px_rgba(37,99,235,.28)]"
      : active
        ? "border-blue-400/25 bg-blue-500/12 text-white"
        : "border-white/[.08] bg-white/[.045] text-slate-200 hover:border-white/[.14] hover:bg-white/[.075]",
  );
  const content = <><span className={cn("grid shrink-0 place-items-center rounded-xl border", compact ? "h-8 w-8" : "h-9 w-9", primary ? "border-white/15 bg-white/10" : active ? "border-blue-400/20 bg-blue-500/10" : "border-white/[.07] bg-black/15")}><Icon className={cn(compact ? "h-4 w-4" : "h-[18px] w-[18px]", primary ? "text-white" : active ? "text-blue-300" : "text-slate-400 group-hover:text-white")} /></span><span className="min-w-0 flex-1 truncate text-left font-semibold">{label}</span><ChevronRight className={cn("h-4 w-4 shrink-0 transition-transform group-hover:translate-x-0.5", primary ? "text-white/80" : active ? "text-blue-300" : "text-slate-500")} /></>;
  return external ? <a href={href} target="_blank" rel="noopener noreferrer" onClick={onClick} className={style}>{content}</a> : <Link href={href} onClick={onClick} className={style}>{content}</Link>;
}

function MobileNavGroup({ label, icon: Icon, open, onClick, green, children }: { label: string; icon: MobileIcon; open: boolean; onClick: () => void; green?: boolean; children: React.ReactNode }) {
  return <div className={cn("overflow-hidden rounded-2xl border transition-colors", open ? "border-blue-400/20 bg-white/[.065]" : "border-white/[.08] bg-white/[.045]")}><button type="button" onClick={onClick} aria-expanded={open} className="group flex w-full items-center gap-3 px-4 py-3.5 text-[15px] text-slate-200"><span className={cn("grid h-9 w-9 shrink-0 place-items-center rounded-xl border", green ? "border-emerald-400/20 bg-emerald-500/10" : "border-white/[.07] bg-black/15")}><Icon className={cn("h-[18px] w-[18px]", green ? "text-emerald-300" : "text-slate-400 group-hover:text-white")} /></span><span className={cn("flex-1 text-left font-semibold", green && "text-emerald-300")}>{label}</span><ChevronDown className={cn("h-4 w-4 transition-transform duration-200", green ? "text-emerald-300" : "text-slate-500", open && "rotate-180")} /></button>{open && <div className="mx-2 mb-2 space-y-1 border-t border-white/[.07] pt-2">{children}</div>}</div>;
}

function MobileSubLink({ href, label, icon: Icon, close }: { href: string; label: string; icon: MobileIcon; close: () => void }) {
  return <Link href={href} onClick={close} className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium text-slate-400 transition hover:bg-white/[.06] hover:text-white"><Icon className="h-4 w-4 text-blue-300" />{label}<ChevronRight className="ml-auto h-3.5 w-3.5 text-slate-600" /></Link>;
}

export function SiteNav() {
  const { data: session } = useSession();
  const pathname = usePathname();
  const [offen, setOffen] = React.useState(false);
  const [mobileGroup, setMobileGroup] = React.useState<"commands" | "about" | "team" | null>(null);
  const [compact, setCompact] = React.useState(false);

  React.useEffect(() => {
    const update = () => setCompact(window.scrollY > 56);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);

  React.useEffect(() => {
    if (!offen) return;
    const old = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const close = (event: KeyboardEvent) => event.key === "Escape" && setOffen(false);
    window.addEventListener("keydown", close);
    return () => { document.body.style.overflow = old; window.removeEventListener("keydown", close); };
  }, [offen]);

  return (
    <>
    <div className="sticky top-0 z-50 h-[86px] w-full px-2 pt-2 sm:h-[96px] sm:px-4 sm:pt-3">
    <nav
      data-compact={compact ? "true" : "false"}
      className={cn(
        "pointer-events-auto mx-auto overflow-visible rounded-2xl border bg-[#111116]/92 shadow-[0_18px_55px_rgba(0,0,0,.34)] backdrop-blur-2xl transition-[max-width,height,background-color,border-color,box-shadow] duration-500 ease-out",
        compact
          ? "h-[60px] max-w-[1180px] border-blue-400/20 bg-[#101015]/96 shadow-[0_16px_45px_rgba(0,0,0,.48)]"
          : "h-[72px] max-w-[1400px] border-white/10",
      )}
    >
      <div className={cn("flex h-full items-center px-3 transition-[padding,gap] duration-500 sm:px-5", compact ? "gap-3 lg:gap-5" : "gap-4 lg:gap-8 lg:px-8")}>
        {/* Eigenständige Marke wie in der Vorlage: echtes Logo, Name und Claim. */}
        <Link
          href="/"
          className="flex min-w-0 shrink-0 items-center gap-2.5"
          aria-label={`${BRAND} Startseite`}
        >
          <span className={cn("grid shrink-0 place-items-center overflow-hidden rounded-xl border border-blue-400/20 bg-blue-500/10 transition-[width,height] duration-500", compact ? "h-8 w-8" : "h-9 w-9")}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/icon-192.png" alt="" className="h-full w-full object-cover" />
          </span>
          <span className="hidden min-w-0 sm:block">
            <strong className={cn("block truncate font-extrabold leading-none tracking-tight text-white transition-[font-size] duration-500", compact ? "text-[14px]" : "text-[16px]")}>{BRAND}</strong>
            <span className="mt-1 block text-[8px] font-black uppercase tracking-[.24em] text-blue-400">All in one</span>
          </span>
        </Link>

        {/* Die Links. Ab lg sichtbar, darunter im Menü. */}
        <div className={cn("hidden items-center transition-[gap] duration-500 lg:flex", compact ? "gap-4" : "gap-7")}>
          <Dropdown label="Befehle" items={BEFEHLE} />
          <Dropdown label="Über" items={UEBER} />
          <a
            href={SUPPORT_INVITE}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[15px] text-slate-300 hover:text-white transition-colors"
          >
            Support Server
          </a>
          <Link
            href="/dashboard"
            className="text-[15px] text-slate-300 hover:text-white transition-colors"
          >
            Dashboard
          </Link>
          <Dropdown
            label="Team beitreten"
            items={TEAM_ROLLEN}
            tone="emerald"
            icon={UserPlus}
            footer={{ label: "Alle Rollen ansehen", href: "/team/apply" }}
          />
          <a
            href={INVITE_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-[15px] text-slate-300 hover:text-white transition-colors"
          >
            <CirclePlus className="h-4 w-4" />
            Bot hinzufügen
          </a>
        </div>

        {/* Rechts: Sprache und Konto. */}
        <div className="ml-auto flex items-center gap-3">
          <div className="hidden sm:block">
            <LanguageSwitcher />
          </div>

          {session?.user ? (
            <Link
              href="/konto"
              className="flex items-center gap-2 rounded-full border border-slate-800 bg-[#131318] pl-1.5 pr-3 py-1.5 hover:border-slate-700 transition-colors"
            >
              {session.user.image ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={session.user.image}
                  alt=""
                  className="h-7 w-7 rounded-full"
                />
              ) : (
                <span className="h-7 w-7 rounded-full bg-primary/20 grid place-items-center">
                  <LayoutDashboard className="h-3.5 w-3.5 text-primary" />
                </span>
              )}
              <span className="text-[14px] text-slate-200 max-w-[120px] truncate">
                {session.user.name}
              </span>
              <ChevronDown className="h-4 w-4 text-slate-500" />
            </Link>
          ) : (
            <button
              type="button"
              onClick={() =>
                signIn("discord", { callbackUrl: "/auth/success?next=%2Fdashboard" }).catch(() => {})
              }
              className="flex items-center gap-2 rounded-full border border-slate-800 bg-[#131318] px-3 sm:px-4 py-2 text-[14px] text-slate-200 hover:border-slate-700 transition-colors"
            >
              <LogIn className="h-4 w-4 shrink-0" />
              <span className="hidden sm:inline">Anmelden</span>
            </button>
          )}

          {/* Zusätzliches Komplettmenü – auch am PC rechts neben dem Konto. */}
          <button
            type="button"
            onClick={() => setOffen((o) => !o)}
            aria-label="Komplettmenü"
            aria-expanded={offen}
            aria-controls="public-navigation-drawer"
            className="h-9 w-9 grid place-items-center rounded-xl border border-slate-800 text-slate-300 hover:border-slate-700 hover:text-white transition-colors"
          >
            {offen ? (
              <X className="h-4 w-4" />
            ) : (
              <span className="space-y-1">
                <span className="block h-0.5 w-4 bg-current" />
                <span className="block h-0.5 w-4 bg-current" />
                <span className="block h-0.5 w-4 bg-current" />
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Der mobile Drawer liegt bewusst außerhalb der gefilterten Nav:
          so bezieht sich position:fixed zuverlässig auf den Viewport. */}
    </nav>
    </div>
      {offen && (
        <div id="public-navigation-drawer" className="fixed inset-0 z-[100] h-dvh" role="dialog" aria-modal="true" aria-label="Hauptmenü">
          <button aria-label="Menü schließen" onClick={() => setOffen(false)} className="absolute inset-0 bg-[#02030a]/72 backdrop-blur-md" />
          <aside className="absolute bottom-2 right-2 top-2 flex w-[min(88vw,420px)] flex-col overflow-hidden rounded-[28px] border border-white/[.12] bg-[#090b12]/78 shadow-[0_28px_100px_rgba(0,0,0,.72)] backdrop-blur-3xl sm:bottom-4 sm:right-4 sm:top-4">
            <div className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-blue-600/20 blur-3xl" />
            <div className="pointer-events-none absolute -bottom-24 -left-20 h-56 w-56 rounded-full bg-indigo-500/10 blur-3xl" />

            <div className="relative flex items-center gap-3 border-b border-white/[.08] px-4 py-4 sm:px-5">
              <div className="grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-2xl border border-blue-300/20 bg-blue-500/10 shadow-[0_8px_24px_rgba(37,99,235,.18)]">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/icon-192.png" alt="" className="h-full w-full object-cover" />
              </div>
              <div className="min-w-0 flex-1">
                <span className="block truncate text-[17px] font-black tracking-tight text-white">{BRAND}</span>
                <span className="mt-0.5 block text-[9px] font-black uppercase tracking-[.22em] text-blue-300/80">Navigation</span>
              </div>
              <button type="button" onClick={() => setOffen(false)} className="grid h-10 w-10 place-items-center rounded-2xl border border-white/[.08] bg-white/[.045] text-slate-400 transition hover:bg-white/[.09] hover:text-white" aria-label="Menü schließen"><X className="h-5 w-5" /></button>
            </div>

            <div className="relative flex-1 space-y-2 overflow-y-auto px-3 py-3 [scrollbar-width:none] sm:px-4 sm:py-4">
              <MobileNavLink href="/dashboard" label="Dashboard öffnen" icon={LayoutDashboard} primary onClick={() => setOffen(false)} />

              <div className="grid grid-cols-2 gap-2">
                <MobileNavLink href={INVITE_URL} label="Bot hinzufügen" icon={CirclePlus} external compact onClick={() => setOffen(false)} />
                <MobileNavLink href={SUPPORT_INVITE} label="Support" icon={CircleHelp} external compact onClick={() => setOffen(false)} />
              </div>

              <p className="px-1 pb-0.5 pt-3 text-[9px] font-black uppercase tracking-[.2em] text-slate-500">Seiten</p>
              <MobileNavLink href="/" label="Startseite" icon={Home} active={pathname === "/"} onClick={() => setOffen(false)} />

              <MobileNavGroup label="Befehle & Hilfe" icon={Grid2X2} open={mobileGroup === "commands"} onClick={() => setMobileGroup(mobileGroup === "commands" ? null : "commands")}>
                <MobileSubLink href="/commands" label="Alle Befehle" icon={Grid2X2} close={() => setOffen(false)} />
                <MobileSubLink href="/docs" label="Dokumentation" icon={BookOpen} close={() => setOffen(false)} />
              </MobileNavGroup>

              <MobileNavGroup label="Mehr entdecken" icon={Globe} open={mobileGroup === "about"} onClick={() => setMobileGroup(mobileGroup === "about" ? null : "about")}>
                <MobileSubLink href="/premium" label="Premium" icon={Shield} close={() => setOffen(false)} />
                <MobileSubLink href="/status" label="Systemstatus" icon={Activity} close={() => setOffen(false)} />
                <MobileSubLink href="/ideas" label="Community-Ideen" icon={CircleHelp} close={() => setOffen(false)} />
                <MobileSubLink href="/team" label="Unser Team" icon={Users} close={() => setOffen(false)} />
                <MobileSubLink href="/imprint" label="Impressum" icon={FileText} close={() => setOffen(false)} />
                <MobileSubLink href="/privacy" label="Datenschutz" icon={Shield} close={() => setOffen(false)} />
                <MobileSubLink href="/terms" label="Nutzungsbedingungen" icon={FileText} close={() => setOffen(false)} />
              </MobileNavGroup>

              <MobileNavGroup label="Team beitreten" icon={UserPlus} green open={mobileGroup === "team"} onClick={() => setMobileGroup(mobileGroup === "team" ? null : "team")}>
                {TEAM_ROLLEN.map(item => <MobileSubLink key={item.href} href={item.href} label={item.label} icon={UserPlus} close={() => setOffen(false)} />)}
                <MobileSubLink href="/team/apply" label="Alle Bewerbungen" icon={Users} close={() => setOffen(false)} />
              </MobileNavGroup>

              <p className="px-1 pb-0.5 pt-3 text-[9px] font-black uppercase tracking-[.2em] text-slate-500">Konto & Ansicht</p>
              {session?.user ? (
                <Link href="/konto" onClick={() => setOffen(false)} className="flex items-center gap-3 rounded-2xl border border-white/[.08] bg-white/[.045] px-4 py-3 text-slate-100 transition hover:bg-white/[.075]">
                  {session.user.image ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={session.user.image} alt="" className="h-9 w-9 rounded-xl ring-1 ring-white/10" />
                  ) : <span className="grid h-9 w-9 place-items-center rounded-xl bg-blue-500/10"><UserRound className="h-5 w-5 text-blue-300" /></span>}
                  <span className="min-w-0 flex-1"><strong className="block truncate text-[14px]">{session.user.name}</strong><span className="block text-[10px] text-slate-500">Mein Konto</span></span><ChevronRight className="h-4 w-4 text-slate-500" />
                </Link>
              ) : (
                <button onClick={() => signIn("discord", { callbackUrl: "/auth/success?next=%2Fdashboard" })} className="flex w-full items-center gap-3 rounded-2xl border border-white/[.08] bg-white/[.045] px-4 py-3 text-left text-slate-100 transition hover:bg-white/[.075]">
                  <span className="grid h-9 w-9 place-items-center rounded-xl bg-blue-500/10"><LogIn className="h-4 w-4 text-blue-300" /></span><span className="flex-1 text-[14px] font-semibold">Mit Discord anmelden</span><ChevronRight className="h-4 w-4 text-slate-500" />
                </button>
              )}

              <div className="flex items-center gap-3 rounded-2xl border border-white/[.08] bg-white/[.045] px-4 py-3">
                <span className="flex-1 text-[12px] font-semibold text-slate-400">Design & Sprache</span>
                <ThemeToggle embedded />
                <div className="h-8 w-px bg-white/[.08]" />
                <LanguageSwitcher />
              </div>
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
