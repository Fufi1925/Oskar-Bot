"use client";

/**
 * Gemeinsame Fußzeile für alle öffentlichen Website-Seiten.
 *
 * Sie sitzt bewusst im Root-Layout statt in jeder einzelnen Seite. So können
 * Startseite, Status, Dokumentation, Team und Rechtstexte nicht mehr mit
 * unterschiedlichen oder vergessenen Fußzeilen auseinanderlaufen. Das
 * eigentliche Dashboard bleibt ausgenommen: dort gehört die linke
 * Arbeitsnavigation bis an den unteren Rand.
 */

import { brandAsset, normalisiereMarke } from "@/lib/brand";
import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLanguage } from "@/lib/i18n/LanguageContext";
import { INVITE_URL } from "@/components/site-nav";
import styles from "./public-footer.module.css";
import {
  Github,
  Mail,
  MessageCircle,
} from "lucide-react";

const BRAND = normalisiereMarke(process.env.NEXT_PUBLIC_BRAND_NAME);
const TIKTOK_URL =
  "https://www.tiktok.com/@university6421?_r=1&_t=ZG-99Xn7K24Gfp";

function TikTokIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className={className}>
      <path d="M15.3 3c.2 1.7 1.2 3.1 2.7 4a7 7 0 0 0 3 1v3.2a10 10 0 0 1-5.7-1.8v6.3a6.3 6.3 0 1 1-5.4-6.2v3.3a3.1 3.1 0 1 0 2.2 3V3h3.2Z" />
    </svg>
  );
}

function SocialLink({
  href,
  label,
  children,
}: {
  href: string;
  label: string;
  children: React.ReactNode;
}) {
  const external = href.startsWith("http");
  return (
    <a
      href={href}
      aria-label={label}
      title={label}
      target={external ? "_blank" : undefined}
      rel={external ? "noopener noreferrer" : undefined}
      className="grid h-10 w-10 place-items-center rounded-xl border border-white/10 bg-white/[0.02] text-zinc-400 transition-colors hover:border-white/25 hover:text-white"
    >
      {children}
    </a>
  );
}

function LiveStatus() {
  const { language } = useLanguage();
  const [online, setOnline] = React.useState<boolean | null>(null);

  React.useEffect(() => {
    let active = true;
    let request = 0;

    const load = async () => {
      const current = ++request;
      try {
        const response = await fetch("/api/status", {
          cache: "no-store",
          signal: AbortSignal.timeout(5000),
        });
        const result = await response.json();
        if (active && current === request) {
          setOnline(Boolean(result?.ok && result?.data?.state === "online"));
        }
      } catch {
        if (active && current === request) setOnline(false);
      }
    };

    load();
    const timer = window.setInterval(load, 60_000);
    return () => {
      active = false;
      request += 1;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <Link
      href="/status"
      className="inline-flex items-center gap-2 rounded-full border border-slate-800 bg-[#0d0d10] px-3.5 py-2 text-[12px] font-semibold text-slate-400 transition-colors hover:border-slate-700 hover:text-white"
    >
      <span className="relative flex h-2.5 w-2.5">
        {online === true && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-30" />
        )}
        <span
          className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
            online === true
              ? "bg-emerald-400"
              : online === false
                ? "bg-rose-400"
                : "bg-slate-600"
          }`}
        />
      </span>
      {online === true
        ? (language === "en" ? "All systems operational" : "Alle Systeme betriebsbereit")
        : online === false
          ? (language === "en" ? "Check status" : "Status prüfen")
          : (language === "en" ? "Checking status …" : "Status wird geprüft …")}
    </Link>
  );
}

export function PublicFooter({ supportInvite, email }: { supportInvite: string; email: string }) {
  const pathname = usePathname();
  const { language } = useLanguage();
  const copy = (de: string, en: string) => language === "en" ? en : de;

  if (["/dashboard", "/api/", "/auth/", "/Tickets/Transkript/", "/526etrzeqwgoqfu32qzi", "/wartung"].some((path) => pathname.startsWith(path))) return null;

  const groups = [
    { title: copy("Produkt", "Product"), links: [
      [copy("Bot einladen", "Invite bot"), INVITE_URL],
      ["Dashboard", "/dashboard"],
      ["Premium", "/premium"],
      [copy("Kaufanfrage stellen", "Request premium"), "/dashboard/premium"],
      [copy("Alle Befehle", "All commands"), "/commands"],
    ] },
    { title: copy("Ressourcen", "Resources"), links: [
      [copy("Dokumentation", "Documentation"), "/docs"],
      ["FAQ", "/#faq"],
      [copy("Systemstatus", "System status"), "/status"],
      ["Support", supportInvite],
      ...(email ? [[copy("Kontakt", "Contact"), `mailto:${email}`]] : []),
    ] },
    { title: copy("Mitmachen", "Get involved"), links: [
      [copy("Community-Ideen", "Community ideas"), "/ideas"],
      [copy("Unser Team", "Our team"), "/team"],
      [copy("Team beitreten", "Join the team"), "/team/apply"],
      ["GitHub", "https://github.com/Fufi1925/Oskar-Bot"],
      ["TikTok", TIKTOK_URL],
    ] },
  ];

  return (
    <footer data-no-translate className={styles.footer}>
      <div className={styles.container}>
        <div className={styles.columns}>
          <div className={styles.brand}>
            <Link href="/" className={styles.brandLink}><img src={brandAsset("icon-192.png")} width={40} height={40} alt="" /><span>{BRAND}<small>DISCORD. SIMPLIFIED.</small></span></Link>
            <p>{copy("Ein Bot für Moderation, Tickets und Automationen. Mehr Überblick für dich. Mehr Raum für deine Community.", "One bot for moderation, tickets and automation. More clarity for you. More room for your community.")}</p>
            <LiveStatus />
          </div>
          {groups.map((group) => <div key={group.title}><h2>{group.title}</h2><nav aria-label={group.title}>{group.links.map(([label, href]) => href.startsWith("/") ? <Link key={label} href={href}>{label}</Link> : <a key={label} href={href} target={href.startsWith("https:") ? "_blank" : undefined} rel={href.startsWith("https:") ? "noopener noreferrer" : undefined}>{label}</a>)}</nav></div>)}
        </div>
        <nav className={styles.legal} aria-label={copy("Rechtliche Informationen", "Legal information")}>
          <Link href="/imprint">{copy("Impressum", "Legal notice")}</Link>
          <Link href="/privacy">{copy("Datenschutz", "Privacy")}</Link>
          <Link href="/terms">{copy("Nutzungsbedingungen", "Terms of Service")}</Link>
          {email && <a href={`mailto:${email}`}>{copy("Kontakt", "Contact")}</a>}
        </nav>
        <div className={styles.bottom}>
          <p><img src={brandAsset("favicon-32.png")} width={20} height={20} alt="" />© 2026 {BRAND}. {copy("Alle Rechte vorbehalten.", "All rights reserved.")}</p>
          <div className={styles.socials}>
            <SocialLink href="https://github.com/Fufi1925/Oskar-Bot" label="GitHub"><Github size={17} /></SocialLink>
            <SocialLink href={TIKTOK_URL} label="TikTok"><TikTokIcon className="h-[17px] w-[17px]" /></SocialLink>
            <SocialLink href={supportInvite} label={copy("Discord Support-Server", "Discord support server")}><MessageCircle size={17} /></SocialLink>
            {email && <SocialLink href={`mailto:${email}`} label={copy("E-Mail", "Email")}><Mail size={17} /></SocialLink>}
          </div>
        </div>
        <div className={styles.wordmark} aria-hidden="true">CLOUDTIX</div>
      </div>
    </footer>
  );
}
