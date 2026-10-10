"use client";

import React from "react";
import Link from "next/link";
import {
  ArrowDown, ArrowRight, AudioLines, Check, ChevronDown, Crown,
  LayoutDashboard, MessageSquareText, ShieldCheck, Ticket, Users, Zap,
} from "lucide-react";
import { INVITE_URL, SiteNav } from "@/components/site-nav";
import { FeaturedServerMarquee } from "@/components/home/featured-server-marquee";
import { BRAND, BRAND_LOGO, brandAsset } from "@/lib/brand";
import { useLanguage } from "@/lib/i18n/LanguageContext";
import { SUPPORT_INVITE } from "@/lib/legal";
import styles from "./cloudtix-homepage.module.css";

type Numbers = { guilds: number; users: number; modules: number; commands: number };
type Copy = (de: string, en: string) => string;

const FEATURES = [
  { icon: ShieldCheck, title: ["Ein sicherer Server.", "A safer server."], text: ["Anti-Nuke, AutoMod und Verifizierung. Schutz, den du einmal einrichtest und gezielt an deinen Server anpasst.", "Anti-Nuke, AutoMod and verification. Set up protection once and adapt it to your server."], tag: ["Sicherheit", "Security"] },
  { icon: Ticket, title: ["Support mit Struktur.", "Support with structure."], text: ["Tickets, Teamrechte und Transkripte halten Anfragen zusammen. Damit keine Nachricht untergeht.", "Tickets, staff permissions and transcripts keep requests together. So no message gets lost."], tag: ["Tickets & Support", "Tickets & support"] },
  { icon: Users, title: ["Mehr Miteinander.", "More community."], text: ["Begrüßungen, Level, Rollen und Gewinnspiele geben deiner Community einen Ort, an dem sie gerne bleibt.", "Welcome messages, levels, roles and giveaways make your community a place people want to stay."], tag: ["Community", "Community"] },
  { icon: Zap, title: ["Weniger Routine.", "Less routine."], text: ["Eigene Befehle, automatische Antworten und Logs übernehmen die kleinen Dinge im Hintergrund.", "Custom commands, automatic replies and logs take care of the little things in the background."], tag: ["Automationen", "Automation"] },
  { icon: AudioLines, title: ["Platz für Gespräche.", "Room for conversation."], text: ["Musik, temporäre Sprachkanäle und Support-Warteräume. Alles dort, wo deine Community zusammenkommt.", "Music, temporary voice channels and support queues. Right where your community comes together."], tag: ["Voice & Musik", "Voice & music"] },
  { icon: Users, title: ["Ein Team, das zusammenpasst.", "A team that works together."], text: ["Bewerbungen, Teamlisten und Rollen bringen Ordnung in die Zusammenarbeit auf deinem Server.", "Applications, team lists and roles bring structure to collaboration on your server."], tag: ["Team & Rollen", "Team & roles"] },
  { icon: MessageSquareText, title: ["Gute Ideen bleiben.", "Good ideas stay."], text: ["Vorschläge teilen, gemeinsam diskutieren und abstimmen. Deine Community hilft CloudTIX weiter.", "Share suggestions, discuss them and vote together. Your community helps CloudTIX improve."], tag: ["Community-Ideen", "Community ideas"], href: "/ideas" },
];

const FAQ = [
  [["Kann ich CloudTIX kostenlos nutzen?", "Can I use CloudTIX for free?"], ["Ja. Die wichtigsten Module sind kostenlos. Premium erweitert Limits und ergänzt Funktionen wie individuelles Bot-Design, zusätzliche Backups und User Pull.", "Yes. The main modules are free. Premium increases limits and adds features such as custom bot design, additional backups and User Pull."]],
  [["Wie richte ich meinen Server ein?", "How do I set up my server?"], ["Lade CloudTIX auf deinen Server ein und öffne das Dashboard. Melde dich mit Discord an, wähle deinen Server und aktiviere die Module, die du brauchst.", "Invite CloudTIX to your server and open the dashboard. Sign in with Discord, choose your server and enable the modules you need."]],
  [["Brauche ich Programmierkenntnisse?", "Do I need coding skills?"], ["Nein. Du verwaltest deinen Server über Formulare im Dashboard. Die Dokumentation hilft dir bei der Einrichtung der einzelnen Funktionen.", "No. Manage your server through dashboard forms. The documentation helps you set up each feature."]],
  [["Kann ich einzelne Module ausschalten?", "Can I turn individual modules off?"], ["Ja. Du entscheidest für jeden Server, welche Module aktiv sind. CloudTIX passt sich deiner Community an.", "Yes. You choose which modules are active on each server. CloudTIX adapts to your community."]],
];

function FaqRow({ question, answer }: { question: string; answer: string }) {
  const id = React.useId();
  const [open, setOpen] = React.useState(false);
  return (
    <div className={styles.faqRow}>
      <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        {question}<ChevronDown className={open ? styles.chevronOpen : ""} size={18} />
      </button>
      <div id={id} hidden={!open}><p>{answer}</p></div>
    </div>
  );
}

function DashboardPreview({ copy }: { copy: Copy }) {
  return (
    <div className={styles.dashboardPreview} aria-label={copy("Dashboard-Vorschau", "Dashboard preview")}>
      <div className={styles.previewBar}>
        <span className={styles.previewDots} aria-hidden="true"><i /><i /><i /></span>
        <span>{BRAND} / {copy("Dein Server", "Your server")}</span>
        <LayoutDashboard size={13} aria-hidden="true" />
      </div>
      <div className={styles.previewBody}>
        <div className={styles.previewSidebar} aria-hidden="true">
          <img src={brandAsset("icon-192.png")} alt="" width={30} height={30} />
          <LayoutDashboard size={17} /><ShieldCheck size={17} /><Ticket size={17} /><Users size={17} />
        </div>
        <div className={styles.previewContent}>
          <span className={styles.eyebrow}>{copy("ALLES AN EINEM ORT", "EVERYTHING IN ONE PLACE")}</span>
          <h3>{copy("Dein Server. Dein Überblick.", "Your server. Your overview.")}</h3>
          <div className={styles.previewModules}>
            {[[ShieldCheck, copy("Sicherheit", "Security")], [Ticket, "Tickets"], [Users, "Community"]].map(([Icon, label]) => {
              const ModuleIcon = Icon as typeof ShieldCheck;
              return <div key={label as string}><ModuleIcon size={17} aria-hidden="true" /><span>{label as string}</span><Check size={12} aria-hidden="true" /></div>;
            })}
          </div>
          <div className={styles.previewActivity}><span /><div><strong>{copy("Alles übersichtlich.", "Everything at a glance.")}</strong><p>{copy("Module und Einstellungen zentral verwalten.", "Manage modules and settings in one place.")}</p></div><ArrowRight size={16} aria-hidden="true" /></div>
        </div>
      </div>
    </div>
  );
}

export function CloudtixHomepage() {
  const { language } = useLanguage();
  const copy: Copy = (de, en) => language === "en" ? en : de;
  const [numbers, setNumbers] = React.useState<Numbers | null>(null);
  const [loadingNumbers, setLoadingNumbers] = React.useState(true);

  React.useEffect(() => {
    const controller = new AbortController();
    fetch("/api/bot/bot/numbers", { signal: controller.signal })
      .then((response) => response.ok ? response.json() : null)
      .then((data) => { if (!controller.signal.aborted && data) setNumbers(data); })
      .catch(() => {})
      .finally(() => { if (!controller.signal.aborted) setLoadingNumbers(false); });
    return () => controller.abort();
  }, []);

  const format = (value: number | undefined) => typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString(language === "en" ? "en-US" : "de-DE") : "—";

  return (
    <main className={`${styles.home} cloudtix-dotted`}>
      <SiteNav />
      <div className={styles.container} data-no-translate>
        <section className={styles.hero} aria-labelledby="cloudtix-title">
          <picture className={styles.heroArtwork}>
            <img src="/banner_cloudtix_nur_wolken_weiss.gif" alt={copy("Animierte Wolken mit dem CloudTIX-Logo", "Animated clouds with the CloudTIX logo")} width={1000} height={400} fetchPriority="high" />
          </picture>
          <div className={styles.heroShade} aria-hidden="true" />
          <div className={styles.heroEmblem} aria-hidden="true">
            <img src={BRAND_LOGO} alt="" width={126} height={126} />
          </div>
          <div className={styles.heroContent}>
            <span className={styles.heroBadge}><span />{copy("Ein Bot. Dein ganzer Server.", "One bot. Your whole server.")}</span>
            <p className={styles.heroBrand}>{BRAND}</p>
            <h1 id="cloudtix-title">{copy("Weniger Aufwand.", "Less effort.")}<br /><span>{copy("Mehr Community.", "More community.")}</span></h1>
            <p className={styles.heroDescription}>{copy("Schutz, Tickets und Automationen für deinen Discord. Alles verbunden. Alles unter deiner Kontrolle.", "Protection, tickets and automation for your Discord. All connected. All under your control.")}</p>
            <div className={styles.actions}>
              <a href={INVITE_URL} target="_blank" rel="noopener noreferrer" className={styles.primaryButton}>{copy("CloudTIX einladen", "Invite CloudTIX")}<ArrowRight size={16} /></a>
              <Link href="/dashboard" className={styles.secondaryButton}><LayoutDashboard size={16} />{copy("Dashboard öffnen", "Open dashboard")}</Link>
            </div>
            <p className={styles.heroNote}><Check size={13} />{copy("Kostenlos starten. Ohne Programmierkenntnisse.", "Start for free. No coding skills needed.")}</p>
          </div>
          <a href="#features" className={styles.heroExplore}>{copy("Entdecken", "Explore")}<ArrowDown size={13} /></a>
        </section>

        <section className={styles.stats} aria-label={copy("CloudTIX in Zahlen", "CloudTIX in numbers")} aria-busy={loadingNumbers}>
          {[[numbers?.guilds, copy("Server", "Servers")], [numbers?.users, copy("Mitglieder", "Members")], [numbers?.modules, copy("Module", "Modules")], [numbers?.commands, copy("Befehle", "Commands")]].map(([value, label]) => <div key={label as string}><strong>{format(value as number | undefined)}</strong><span>{label as string}</span></div>)}
        </section>
      </div>

      <FeaturedServerMarquee />

      <section id="features" data-no-translate className={`${styles.container} ${styles.section}`} aria-labelledby="features-title">
        <div className={styles.sectionHeading}>
          <div><p className={styles.eyebrow}>{copy("WENIGER KOMPLEXITÄT", "LESS COMPLEXITY")}</p><h2 id="features-title">{copy("Alles, was dein Server braucht.", "Everything your server needs.")}</h2></div>
          <p>{copy("Ein System für die kleinen Aufgaben und die großen Momente deiner Community.", "One system for the small tasks and the big moments in your community.")}</p>
        </div>
        <div className={styles.featureGrid}>
          <article className={styles.dashboardCard}>
            <div><span className={styles.featureIcon}><LayoutDashboard size={21} /></span><p className={styles.eyebrow}>DASHBOARD</p><h3>{copy("Ein Ort. Alles im Blick.", "One place. Everything in view.")}</h3><p>{copy("Module einrichten, Rechte verwalten und Einstellungen anpassen. Klar aufgebaut, direkt im Browser.", "Set up modules, manage permissions and adjust settings. Clearly arranged, right in your browser.")}</p><Link href="/dashboard" className={styles.textLink}>{copy("Dashboard öffnen", "Open dashboard")}<ArrowRight size={15} /></Link></div>
            <DashboardPreview copy={copy} />
          </article>
          {FEATURES.map((feature) => <article key={feature.title[0]} className={styles.featureCard}><div className={styles.cardTop}><span className={styles.featureIcon}><feature.icon size={21} /></span><span className={styles.featureTag}>{copy(feature.tag[0], feature.tag[1])}</span></div><h3>{copy(feature.title[0], feature.title[1])}</h3><p>{copy(feature.text[0], feature.text[1])}</p><Link href={feature.href || "/docs"} className={styles.textLink}>{copy("Mehr erfahren", "Learn more")}<ArrowRight size={15} /></Link></article>)}
        </div>
      </section>

      <section data-no-translate className={styles.moduleBand} aria-label={copy("CloudTIX-Funktionen", "CloudTIX features")}>
        <div className={styles.moduleRail}>
          <div className={styles.moduleTrack}>
            {[0, 1, 2].map((repeat) => <div key={repeat} className={styles.moduleRun} aria-hidden={repeat > 0}>{[
              copy("TICKET-SYSTEM", "TICKET SYSTEM"), copy("VERIFIZIERUNG", "VERIFICATION"), "MODERATION", "AUTOMOD", "ANTI-NUKE", "LEVELING", "COMMUNITY", copy("AUTOMATIONEN", "AUTOMATION"),
            ].map((module) => <span key={module}>{module}<i aria-hidden="true" /></span>)}</div>)}
          </div>
        </div>
      </section>

      <section data-no-translate className={`${styles.container} ${styles.section} ${styles.setup}`} aria-labelledby="setup-title">
        <div><p className={styles.eyebrow}>{copy("EINFACH ANFANGEN", "GET STARTED")}</p><h2 id="setup-title">{copy("In drei Schritten bei dir.", "Yours in three steps.")}</h2><p>{copy("Kein Bot-Chaos. Kein Rätselraten. Du entscheidest, was dein Server braucht.", "No bot clutter. No guesswork. You decide what your server needs.")}</p><Link href="/docs" className={styles.textLink}>{copy("Zur Einrichtung", "Setup guide")}<ArrowRight size={15} /></Link></div>
        <ol className={styles.steps}>
          {[
            [copy("Einladen", "Invite"), copy("Füge CloudTIX zu deinem Discord-Server hinzu.", "Add CloudTIX to your Discord server."), INVITE_URL],
            [copy("Verbinden", "Connect"), copy("Melde dich mit Discord an und wähle deinen Server.", "Sign in with Discord and choose your server."), "/dashboard"],
            [copy("Einrichten", "Set up"), copy("Aktiviere deine Module. Den Rest bestimmst du.", "Enable your modules. You take it from there."), "/docs"],
          ].map(([title, text, href], index) => <li key={index}><span className={styles.stepNumber}>0{index + 1}</span><div><h3>{href.startsWith("https:") ? <a href={href} target="_blank" rel="noopener noreferrer">{title}<ArrowRight size={15} /></a> : <Link href={href}>{title}<ArrowRight size={15} /></Link>}</h3><p>{text}</p></div></li>)}
        </ol>
      </section>

      <section id="premium" data-no-translate className={`${styles.container} ${styles.section}`} aria-labelledby="premium-title">
        <div className={styles.premiumCard}>
          <div><span className={styles.premiumBadge}><Crown size={14} />{BRAND} PREMIUM</span><h2 id="premium-title">{copy("Für alle, die mehr vorhaben.", "For those with bigger plans.")}</h2><p>{copy("Mehr Spielraum für deine Community. Zusätzliche Möglichkeiten für die Server, die dir wichtig sind.", "More room for your community. Extra possibilities for the servers that matter to you.")}</p><div className={styles.actions}><Link href="/dashboard/premium" className={styles.primaryButton}>{copy("Kaufanfrage stellen", "Request premium")}<ArrowRight size={16} /></Link><Link href="/premium" className={styles.textLink}>{copy("Alle Vorteile", "All benefits")}<ArrowRight size={15} /></Link></div></div>
          <ul className={styles.premiumBenefits}>{[
            copy("3 feste Serverplätze", "3 fixed server slots"), copy("Individuelles Bot-Design", "Custom bot design"), copy("Erweiterte Backups", "Extended backups"), copy("Höhere Limits für eigene Befehle", "Higher custom command limits"), copy("Server-Statistiken", "Server statistics"), copy("User Pull für Server-Owner", "User Pull for server owners"),
          ].map((benefit) => <li key={benefit}><Check size={15} />{benefit}</li>)}</ul>
        </div>
      </section>

      <section id="faq" data-no-translate className={`${styles.container} ${styles.section} ${styles.faq}`} aria-labelledby="faq-title">
        <div><p className={styles.eyebrow}>{copy("GUT ZU WISSEN", "GOOD TO KNOW")}</p><h2 id="faq-title">{copy("Noch Fragen?", "Any questions?")}</h2><p>{copy("Wir helfen dir gerne weiter.", "We're happy to help.")}</p><a href={SUPPORT_INVITE} target="_blank" rel="noopener noreferrer" className={styles.textLink}><MessageSquareText size={16} />{copy("Support kontaktieren", "Contact support")}<ArrowRight size={15} /></a></div>
        <div>{FAQ.map(([question, answer]) => <FaqRow key={question[0]} question={copy(question[0], question[1])} answer={copy(answer[0], answer[1])} />)}</div>
      </section>

      <section data-no-translate className={`${styles.container} ${styles.finalSection}`} aria-labelledby="start-title">
        <div className={styles.finalCard}><img src={brandAsset("icon-192.png")} width={58} height={58} alt="" /><p className={styles.eyebrow}>{BRAND}</p><h2 id="start-title">{copy("Deine Community. Dein nächster Schritt.", "Your community. Your next step.")}</h2><p>{copy("Mach Platz für das, was deinen Server ausmacht.", "Make room for what makes your server yours.")}</p><a href={INVITE_URL} target="_blank" rel="noopener noreferrer" className={styles.primaryButton}>{copy("CloudTIX einladen", "Invite CloudTIX")}<ArrowRight size={16} /></a></div>
      </section>
    </main>
  );
}
