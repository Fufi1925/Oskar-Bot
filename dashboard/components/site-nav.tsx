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

const BRAND = process.env.NEXT_PUBLIC_BRAND_NAME || "University Bot";

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

function MobileNavLink({ href, label, icon: Icon, onClick, external, active, primary }: { href: string; label: string; icon: MobileIcon; onClick: () => void; external?: boolean; active?: boolean; primary?: boolean }) {
  const style = cn(
    "flex w-full items-center gap-4 rounded-2xl px-5 py-4 text-[18px] transition-colors",
    primary ? "bg-[#5865f2] text-white" : active ? "bg-[#23242a] text-white" : "bg-[#1d1e22] text-slate-200 hover:bg-[#25262b]"
  );
  const content = <><Icon className={cn("h-6 w-6", primary ? "text-white" : active ? "text-blue-400" : "text-slate-400")} /><span className="flex-1 text-left">{label}</span><ChevronRight className={cn("h-5 w-5", primary ? "text-white" : "text-blue-500")} /></>;
  return external ? <a href={href} target="_blank" rel="noopener noreferrer" onClick={onClick} className={style}>{content}</a> : <Link href={href} onClick={onClick} className={style}>{content}</Link>;
}

function MobileNavGroup({ label, icon: Icon, open, onClick, green, children }: { label: string; icon: MobileIcon; open: boolean; onClick: () => void; green?: boolean; children: React.ReactNode }) {
  return <div><button type="button" onClick={onClick} aria-expanded={open} className="flex w-full items-center gap-4 rounded-2xl bg-[#1d1e22] px-5 py-4 text-[18px] text-slate-200 hover:bg-[#25262b]"><Icon className={cn("h-6 w-6", green ? "text-emerald-400" : "text-slate-400")} /><span className={cn("flex-1 text-left", green && "text-emerald-400")}>{label}</span><ChevronDown className={cn("h-5 w-5 transition-transform", green ? "text-emerald-400" : "text-slate-300", open && "rotate-180")} /></button>{open && <div className="mt-2 space-y-1 rounded-2xl border border-slate-800 bg-[#15161a] p-2">{children}</div>}</div>;
}

function MobileSubLink({ href, label, icon: Icon, close }: { href: string; label: string; icon: MobileIcon; close: () => void }) {
  return <Link href={href} onClick={close} className="flex items-center gap-3 rounded-xl px-4 py-3 text-[15px] text-slate-400 hover:bg-white/[0.04] hover:text-white"><Icon className="h-4 w-4 text-blue-400" />{label}</Link>;
}

export function SiteNav() {
  const { data: session } = useSession();
  const pathname = usePathname();
  const [offen, setOffen] = React.useState(false);
  const [mobileGroup, setMobileGroup] = React.useState<"commands" | "about" | "team" | null>(null);

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
    <nav className="sticky top-0 z-50 w-full border-b border-slate-800 bg-[#0a0a0c]/90 backdrop-blur-xl">
      <div className="mx-auto max-w-[1400px] px-4 sm:px-6 lg:px-12 xl:px-20 h-[76px] flex items-center gap-4 lg:gap-8">
        {/* Marke — reiner Text, kein Kästchen davor. */}
        <Link
          href="/"
          className="text-[19px] sm:text-[21px] font-extrabold tracking-tight text-white truncate max-w-[46vw] sm:max-w-none"
        >
          {BRAND}
        </Link>

        {/* Die Links. Ab lg sichtbar, darunter im Menü. */}
        <div className="hidden lg:flex items-center gap-7">
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
      {offen && (
        <div id="public-navigation-drawer" className="fixed inset-0 top-0 z-[100] h-dvh" role="dialog" aria-modal="true" aria-label="Hauptmenü">
          <button aria-label="Menü schließen" onClick={() => setOffen(false)} className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
          <aside className="absolute right-0 top-0 flex h-full w-[min(82vw,530px)] flex-col border-l border-slate-700 bg-[#101113] shadow-2xl shadow-black/70">
            <div className="flex items-center gap-4 border-b border-slate-700 px-6 py-7">
              <div className="grid h-11 w-11 place-items-center overflow-hidden rounded-xl border border-blue-500/20 bg-blue-500/10">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/icon-192.png" alt="" className="h-full w-full object-cover" />
              </div>
              <span className="min-w-0 flex-1 truncate text-[22px] font-extrabold text-white">{BRAND}</span>
              <button type="button" onClick={() => setOffen(false)} className="rounded-xl p-2 text-slate-400 hover:bg-white/5 hover:text-white" aria-label="Menü schließen"><X className="h-6 w-6" /></button>
            </div>

            <div className="flex-1 space-y-3 overflow-y-auto px-5 py-6">
              <MobileNavLink href="/" label="Home" icon={Home} active={pathname === "/"} onClick={() => setOffen(false)} />
              <MobileNavLink href="/konto" label="Mein Konto" icon={UserRound} active={pathname === "/konto"} onClick={() => setOffen(false)} />

              <MobileNavGroup label="Commands" icon={Grid2X2} open={mobileGroup === "commands"} onClick={() => setMobileGroup(mobileGroup === "commands" ? null : "commands")}>
                <MobileSubLink href="/commands" label="Alle Befehle" icon={Grid2X2} close={() => setOffen(false)} />
                <MobileSubLink href="/docs" label="Dokumentation" icon={BookOpen} close={() => setOffen(false)} />
              </MobileNavGroup>

              <MobileNavGroup label="Über" icon={Globe} open={mobileGroup === "about"} onClick={() => setMobileGroup(mobileGroup === "about" ? null : "about")}>
                <MobileSubLink href="/premium" label="Premium" icon={Shield} close={() => setOffen(false)} />
                <MobileSubLink href="/status" label="Status" icon={Activity} close={() => setOffen(false)} />
                <MobileSubLink href="/team" label="Team" icon={Users} close={() => setOffen(false)} />
                <MobileSubLink href="/imprint" label="Impressum" icon={FileText} close={() => setOffen(false)} />
                <MobileSubLink href="/privacy" label="Datenschutz" icon={Shield} close={() => setOffen(false)} />
                <MobileSubLink href="/terms" label="Nutzungsbedingungen" icon={FileText} close={() => setOffen(false)} />
              </MobileNavGroup>

              <div className="my-5 h-px bg-slate-700" />
              <MobileNavLink href={SUPPORT_INVITE} label="Support Server" icon={CircleHelp} external onClick={() => setOffen(false)} />

              <MobileNavGroup label="Team beitreten" icon={UserPlus} green open={mobileGroup === "team"} onClick={() => setMobileGroup(mobileGroup === "team" ? null : "team")}>
                {TEAM_ROLLEN.map(item => <MobileSubLink key={item.href} href={item.href} label={item.label} icon={UserPlus} close={() => setOffen(false)} />)}
                <MobileSubLink href="/team/apply" label="Alle Bewerbungen" icon={Users} close={() => setOffen(false)} />
              </MobileNavGroup>

              <MobileNavLink href="/dashboard" label="Dashboard" icon={LayoutDashboard} primary onClick={() => setOffen(false)} />
              <MobileNavLink href={INVITE_URL} label="Bot hinzufügen" icon={CirclePlus} external onClick={() => setOffen(false)} />

              <div className="flex items-center gap-3 rounded-2xl border border-slate-700 bg-[#1d1e22] p-4">
                <span className="flex-1 text-[15px] font-semibold text-slate-300">Design</span>
                <ThemeToggle embedded />
                <div className="h-9 w-px bg-slate-700" />
                <LanguageSwitcher />
              </div>

              {session?.user ? (
                <Link href="/konto" onClick={() => setOffen(false)} className="flex items-center gap-4 rounded-2xl bg-[#27282d] px-5 py-4 text-slate-100">
                  {session.user.image ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={session.user.image} alt="" className="h-9 w-9 rounded-full" />
                  ) : <LayoutDashboard className="h-6 w-6" />}
                  <span className="min-w-0 flex-1 truncate">{session.user.name}</span><ChevronRight className="h-5 w-5" />
                </Link>
              ) : (
                <button onClick={() => signIn("discord", { callbackUrl: "/auth/success?next=%2Fdashboard" })} className="flex w-full items-center gap-4 rounded-2xl bg-[#27282d] px-5 py-4 text-left text-slate-100">
                  <LogIn className="h-6 w-6" /><span className="flex-1 text-[17px]">Anmelden</span><ChevronRight className="h-5 w-5" />
                </button>
              )}
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
