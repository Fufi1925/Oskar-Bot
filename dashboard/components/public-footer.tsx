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

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Bot,
  Heart,
  Mail,
  MessageCircle,
} from "lucide-react";

const BRAND = process.env.NEXT_PUBLIC_BRAND_NAME || "University Bot";
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
      className="grid h-10 w-10 place-items-center rounded-xl border border-slate-800 bg-white/[0.02] text-slate-500 transition-colors hover:border-indigo-500/40 hover:text-indigo-300"
    >
      {children}
    </a>
  );
}

function LiveStatus() {
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
        ? "Status: Alle Systeme aktiv"
        : online === false
          ? "Status prüfen"
          : "Status wird geprüft …"}
    </Link>
  );
}

export function PublicFooter({
  supportInvite,
  email,
}: {
  supportInvite: string;
  email: string;
}) {
  const pathname = usePathname();

  // Interne Arbeits- und Übergangsseiten bekommen keine öffentliche
  // Marketing-Fußzeile. Alle normalen Website-Reiter teilen sie dagegen.
  if (
    pathname.startsWith("/dashboard") ||
    pathname.startsWith("/api/") ||
    pathname.startsWith("/auth/") ||
    pathname.startsWith("/526etrzeqwgoqfu32qzi") ||
    pathname.startsWith("/wartung")
  ) {
    return null;
  }

  return (
    <footer className="relative z-10 border-t border-slate-800/80 bg-[#08080a] px-6 py-12 sm:py-14 lg:px-12 xl:px-20">
      <div className="mx-auto max-w-[1400px]">
        <div className="grid gap-12 md:grid-cols-2 lg:grid-cols-[1.35fr_0.8fr_1fr] lg:gap-16">
          <div>
            <Link href="/" className="inline-flex items-center gap-3 text-white">
              <span className="grid h-10 w-10 place-items-center rounded-xl border border-indigo-500/20 bg-indigo-500/10">
                <Bot className="h-5 w-5 text-indigo-400" />
              </span>
              <span className="text-[20px] font-extrabold tracking-tight">{BRAND}</span>
            </Link>
            <p className="mt-4 max-w-sm text-[14px] leading-6 text-slate-500">
              Der Discord-Bot für Moderation, Tickets, Bewerbungen,
              Verifizierung und eine starke Community.
            </p>

            <div className="mt-6 flex flex-wrap gap-2.5">
              {email && (
                <SocialLink href={`mailto:${email}`} label="E-Mail">
                  <Mail className="h-[18px] w-[18px]" />
                </SocialLink>
              )}
              <SocialLink href={TIKTOK_URL} label="TikTok-Kanal">
                <TikTokIcon className="h-[18px] w-[18px]" />
              </SocialLink>
              <SocialLink href={supportInvite} label="Discord Support-Server">
                <MessageCircle className="h-[18px] w-[18px]" />
              </SocialLink>
            </div>
          </div>

          <div>
            <h2 className="text-[12px] font-extrabold uppercase tracking-[0.18em] text-slate-300">
              Schnellzugriff
            </h2>
            <nav className="mt-5 grid gap-3 text-[14px] text-slate-500" aria-label="Links in der Fußzeile">
              <Link href="/docs" className="w-fit transition-colors hover:text-white">Dokumentation</Link>
              <Link href="/commands" className="w-fit transition-colors hover:text-white">Befehle</Link>
              <Link href="/team" className="w-fit transition-colors hover:text-white">Team</Link>
              <Link href="/terms" className="w-fit transition-colors hover:text-white">Nutzungsbedingungen</Link>
              <Link href="/privacy" className="w-fit transition-colors hover:text-white">Datenschutz</Link>
              <Link href="/imprint" className="w-fit transition-colors hover:text-white">Impressum</Link>
            </nav>
          </div>

          <div>
            <h2 className="text-[12px] font-extrabold uppercase tracking-[0.18em] text-slate-300">
              Kontakt
            </h2>
            <div className="mt-5 grid gap-3 text-[14px] text-slate-500">
              {email && (
                <a href={`mailto:${email}`} className="flex w-fit items-center gap-2 transition-colors hover:text-white">
                  <Mail className="h-4 w-4" />
                  {email}
                </a>
              )}
              <a href={supportInvite} target="_blank" rel="noopener noreferrer" className="w-fit transition-colors hover:text-white">
                Unserem Discord beitreten
              </a>
              <a href={TIKTOK_URL} target="_blank" rel="noopener noreferrer" className="w-fit transition-colors hover:text-white">
                Folge uns auf TikTok
              </a>
            </div>
          </div>
        </div>

        <div className="mt-12 flex flex-col gap-5 border-t border-slate-800/80 pt-7 sm:flex-row sm:items-center sm:justify-between">
          <p className="flex flex-wrap items-center gap-1.5 text-[13px] text-slate-600">
            Erstellt mit <Heart className="h-4 w-4 fill-rose-500/20 text-rose-400" />
            <span className="font-semibold text-slate-400">vom University-Team</span>
            <span aria-hidden>·</span>
            <span>&copy; {2026}</span>
          </p>
          <LiveStatus />
        </div>
      </div>
    </footer>
  );
}
