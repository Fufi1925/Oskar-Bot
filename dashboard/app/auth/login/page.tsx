"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { signIn, useSession } from "next-auth/react";
import { ArrowLeft, Info, Loader2 } from "lucide-react";
import { BRAND, BRAND_LOGO } from "@/lib/brand";
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
      <section data-no-translate className={styles.card} aria-labelledby="login-title">
        <div className={styles.logo}><img src={BRAND_LOGO} alt="" width={76} height={76} /></div>
        <h1 id="login-title">{BRAND}</h1>
        <p className={styles.description}>{copy("Melde dich an, um deine Server zu verwalten, Module einzurichten und deine Community im Blick zu behalten.", "Sign in to manage your servers, configure modules and keep your community running smoothly.")}</p>
        <p className={styles.label}>{copy("ANMELDUNG", "AUTHENTICATION")}</p>
        <button type="button" className={styles.continue} disabled={busy || status === "loading"} onClick={() => void continueWithDiscord()}>
          {busy || status === "loading" ? <Loader2 size={19} className="animate-spin" /> : <DiscordIcon />}
          {busy ? copy("Discord wird geöffnet …", "Opening Discord …") : copy("Mit Discord fortfahren", "Continue with Discord")}
        </button>
        <p className={styles.label}>{copy("INFORMATIONEN", "INFORMATION")}</p>
        <div className={styles.info}><Info size={17} /><p>{copy("Die Anmeldung erfolgt sicher über Discord. Es gelten unsere ", "Sign in securely through Discord. Our ")}<Link href="/terms" target="_blank" rel="noopener noreferrer">{copy("Nutzungsbedingungen", "Terms of Service")}</Link>{copy(". Wie wir deine Daten verarbeiten, erfährst du in der ", " apply. Read about how we process your data in our ")}<Link href="/privacy" target="_blank" rel="noopener noreferrer">{copy("Datenschutzerklärung", "Privacy Policy")}</Link>.</p></div>
      </section>
      <p className={styles.bottom} data-no-translate>{copy("Dein Server. Deine Community. CloudTIX.", "Your server. Your community. CloudTIX.")}</p>
    </main>
  );
}

export default function LoginPage() {
  return <Suspense fallback={<main className={`${styles.page} cloudtix-dotted`} />}><LoginPanel /></Suspense>;
}
