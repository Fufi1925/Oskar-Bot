"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { signIn, useSession } from "next-auth/react";
import { ArrowLeft, ArrowRight, Check, Info, Loader2, ShieldCheck } from "lucide-react";
import { BRAND, BRAND_LOGO, brandAsset } from "@/lib/brand";
import { useLanguage } from "@/lib/i18n/LanguageContext";
import { loginCallbackUrl, loginDestination } from "@/lib/auth-navigation";
import { ThemeToggle } from "@/components/theme-toggle";
import { LanguageSwitcher } from "@/components/language-switcher";
import styles from "./login.module.css";

function DiscordIcon() {
  return <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M19.7 5.3a18 18 0 0 0-4.2-1.4l-.6 1.2a16 16 0 0 0-5.8 0l-.6-1.2a18 18 0 0 0-4.2 1.4C1.6 9.4.9 13.4 1.3 17.3a18 18 0 0 0 5.2 2.6l1.1-1.8-1.7-.8.4-.3a13 13 0 0 0 11.4 0l.4.3-1.7.8 1.1 1.8a18 18 0 0 0 5.2-2.6c.5-4.5-.8-8.5-3-12ZM8.3 14.8c-1.1 0-1.9-1-1.9-2.2s.8-2.2 1.9-2.2 1.9 1 1.9 2.2-.8 2.2-1.9 2.2Zm7.4 0c-1.1 0-1.9-1-1.9-2.2s.8-2.2 1.9-2.2 1.9 1 1.9 2.2-.8 2.2-1.9 2.2Z" /></svg>;
}

function LoginPanel() {
  const router = useRouter();
  const params = useSearchParams();
  const { data: session, status } = useSession();
  const { language } = useLanguage();
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const requested = params.get("next") || params.get("callbackUrl");
  const copy = (de: string, en: string) => language === "en" ? en : de;
  const requestedPath = loginDestination(requested).split(/[?#]/)[0];
  const destinationName = requestedPath.startsWith("/dashboard/admin") ? copy("Admin-Dashboard", "Admin dashboard")
    : requestedPath.startsWith("/dashboard/guild/") ? copy("Serververwaltung", "Server workspace")
    : requestedPath.startsWith("/dashboard/guilds") ? copy("Deine Server", "Your servers")
    : requestedPath.startsWith("/dashboard/premium") ? "Premium"
    : requestedPath === "/dashboard" ? copy("Dein Dashboard", "Your dashboard")
    : copy("Deine ausgewählte Seite", "Your selected page");

  const destination = () => {
    let target = loginDestination(requested, "/dashboard", window.location.origin);
    if (!target.includes("#")) target += window.location.hash;
    return target;
  };

  useEffect(() => {
    if (status === "authenticated" && session?.user?.id && session.accessToken && !session.revoked) {
      let target = loginDestination(requested, "/dashboard", window.location.origin);
      if (!target.includes("#")) target += window.location.hash;
      router.replace(target);
    }
  }, [requested, router, session, status]);

  const continueWithDiscord = async () => {
    if (submitting.current || status === "loading") return;
    submitting.current = true;
    setBusy(true);
    const target = destination();
    try {
      await signIn("discord", { callbackUrl: loginCallbackUrl(target, window.location.origin) });
    } catch {
      submitting.current = false;
      setBusy(false);
      router.replace(`/auth/error?error=OAuthSignin&next=${encodeURIComponent(target)}`);
    }
  };

  return (
    <main className={`${styles.page} cloudtix-dotted`}>
      <div className={styles.topbar}>
        <Link href="/" className={styles.back}><ArrowLeft size={15} />{copy("Zur Startseite", "Back to home")}</Link>
        <div className={styles.controls}><ThemeToggle embedded /><LanguageSwitcher /></div>
      </div>
      <div className={styles.layout} data-no-translate>
      <section className={styles.intro} aria-labelledby="workspace-title">
        <div className={styles.wordmark}><img src={BRAND_LOGO} alt="" width={38} height={38} />{BRAND}<span>WORKSPACE</span></div>
        <p className={styles.eyebrow}>{copy("ALLES FÜR DEINE COMMUNITY", "EVERYTHING FOR YOUR COMMUNITY")}</p>
        <h1 id="workspace-title">{copy("Deine Community.", "Your community.")}<br /><span>{copy("Dein Überblick.", "Your workspace.")}</span></h1>
        <p className={styles.introDescription}>{copy("Von der ersten Begrüßung bis zum letzten Support-Ticket. Gestalte deinen Server mit CloudTIX an einem Ort.", "From the first welcome to the latest support ticket. Shape your server with CloudTIX in one place.")}</p>
        <div className={styles.artwork}><img src={brandAsset("cloudtix_pf weiß.gif")} alt="" width={1000} height={400} /></div>
        <div className={styles.features}>{[copy("Server verwalten", "Manage servers"), copy("Community gestalten", "Build your community"), copy("Schutz einrichten", "Set up protection")].map(label => <span key={label}><Check size={13} />{label}</span>)}</div>
      </section>
      <section className={styles.card} aria-labelledby="login-title">
        <div className={styles.logo}><ShieldCheck size={24} /></div>
        <p className={styles.eyebrow}>{copy("DEIN ZUGANG ZU CLOUDTIX", "YOUR ACCESS TO CLOUDTIX")}</p>
        <h2 id="login-title">{copy("Willkommen zurück.", "Welcome back.")}</h2>
        <p className={styles.description}>{copy("Verbinde dein Discord-Konto und öffne deinen Workspace.", "Connect your Discord account and open your workspace.")}</p>
        <div className={styles.destination}><span>{copy("Nach der Anmeldung", "After signing in")}</span><strong>{destinationName}<ArrowRight size={14} /></strong></div>
        <p className={styles.label}>{copy("ANMELDUNG", "AUTHENTICATION")}</p>
        <button type="button" className={styles.continue} disabled={busy || status === "loading"} onClick={() => void continueWithDiscord()}>
          {busy || status === "loading" ? <Loader2 size={19} className="animate-spin" /> : <DiscordIcon />}
          {busy ? copy("Discord wird geöffnet …", "Opening Discord …") : copy("Mit Discord fortfahren", "Continue with Discord")}
        </button>
        <p className={styles.label}>{copy("INFORMATIONEN", "INFORMATION")}</p>
        <div className={styles.info}><Info size={17} /><p>{copy("Die Anmeldung erfolgt sicher über Discord. Es gelten unsere ", "Sign in securely through Discord. Our ")}<Link href="/terms" target="_blank" rel="noopener noreferrer">{copy("Nutzungsbedingungen", "Terms of Service")}</Link>{copy(". Wie wir deine Daten verarbeiten, erfährst du in der ", " apply. Read about how we process your data in our ")}<Link href="/privacy" target="_blank" rel="noopener noreferrer">{copy("Datenschutzerklärung", "Privacy Policy")}</Link>.</p></div>
        <p className={styles.secure}><ShieldCheck size={13} />{copy("Dein Passwort bleibt bei Discord.", "Your password stays with Discord.")}</p>
      </section>
      </div>
      <p className={styles.bottom} data-no-translate>{copy("Dein Server. Deine Community. CloudTIX.", "Your server. Your community. CloudTIX.")}</p>
    </main>
  );
}

export default function LoginPage() {
  return <Suspense fallback={<main className={`${styles.page} cloudtix-dotted`} />}><LoginPanel /></Suspense>;
}
