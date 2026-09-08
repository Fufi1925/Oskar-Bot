"use client";

import React, { useEffect } from "react";
import { Check } from "lucide-react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { api } from "@/lib/api";

/**
 * Deliberate post-login step. It is a real route rather than a toast on the
 * dashboard so no cookie, premium or support dialog can cover the successful
 * sign-in confirmation before the user has seen it.
 */
export default function LoginSuccessPage() {
  const router = useRouter();
  const { data: session, status } = useSession();
  const sessionUserId = (session?.user as { id?: string } | undefined)?.id;

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/");
      return;
    }
    if (status !== "authenticated") return;

    if (sessionUserId) {
      // Nebenläufig: Die wichtige Erfolgsmeldung bleibt zuerst sichtbar und
      // wartet nicht auf die Sicherheitsprotokollierung.
      void api.recordAccountSession(sessionUserId).catch(() => {});
    }

    let cancelled = false;
    let timer: number | undefined;
    const started = Date.now();
    const requested = new URLSearchParams(window.location.search).get("next");

    void (async () => {
      let destination = requested || "/dashboard";
      if (!requested && sessionUserId) {
        // Account preference is cross-device. Never let a slow API hide the
        // success confirmation or hold the redirect indefinitely.
        const preference: any = await Promise.race([
          api.getAccountPreferences(sessionUserId).catch(() => null),
          new Promise((resolve) =>
            window.setTimeout(() => resolve(null), 1000),
          ),
        ]);
        if (preference) {
          localStorage.setItem("language", preference.language || "de");
          localStorage.setItem(
            "dashboard-theme",
            preference.theme === "light" ? "light" : "dark",
          );
          localStorage.setItem(
            "account-timezone",
            preference.timezone || "Europe/Berlin",
          );
          localStorage.setItem(
            "account-number-format",
            preference.number_format || "de-DE",
          );
          localStorage.setItem(
            "account-date-format",
            preference.date_format || "medium",
          );
          localStorage.setItem(
            "account-start-page",
            preference.start_page || "/dashboard",
          );
          document.documentElement.dataset.theme =
            preference.theme === "light" ? "light" : "dark";
          document.documentElement.lang =
            preference.language === "en" ? "en" : "de";
        }
        destination = preference?.start_page || "/dashboard";
      }
      if (!destination.startsWith("/") || destination.startsWith("//"))
        destination = "/dashboard";
      const remaining = Math.max(0, 1800 - (Date.now() - started));
      timer = window.setTimeout(() => {
        if (!cancelled) router.replace(destination);
      }, remaining);
    })();

    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [router, sessionUserId, status]);

  return (
    <main className="fixed inset-0 z-[10000] grid min-h-screen place-items-center overflow-hidden bg-[#070708] px-5">
      <div className="login-success-glow pointer-events-none absolute h-80 w-80 rounded-full bg-emerald-500/10 blur-3xl" />
      <section
        role="status"
        aria-live="polite"
        className="login-success-card relative w-full max-w-sm overflow-hidden rounded-2xl border border-white/[0.06] bg-[#141415] px-6 py-9 text-center shadow-2xl shadow-black/60 sm:px-10"
      >
        <div className="relative mx-auto h-20 w-20">
          <span className="login-success-ring absolute inset-0 rounded-full border border-emerald-400/30" />
          <div className="login-success-check absolute inset-2 grid place-items-center rounded-full bg-emerald-500 shadow-lg shadow-emerald-500/25">
            <Check className="h-9 w-9 text-white" strokeWidth={2.5} />
          </div>
        </div>
        <h1 className="mt-5 text-2xl font-black text-white">Erfolgreich!</h1>
        <p className="mt-2 text-sm text-slate-300">
          Login erfolgreich! Dashboard wird geladen
          <span className="login-dot">.</span>
          <span className="login-dot">.</span>
          <span className="login-dot">.</span>
        </p>
        <div className="mx-auto mt-6 h-1 w-32 overflow-hidden rounded-full bg-white/5">
          <div className="login-success-progress h-full rounded-full bg-emerald-500" />
        </div>
      </section>
      <style jsx>{`
        .login-success-card {
          animation: card-in 0.42s cubic-bezier(0.2, 0.8, 0.2, 1) both;
        }
        .login-success-check {
          animation: check-in 0.55s 0.12s cubic-bezier(0.2, 1.5, 0.4, 1) both;
        }
        .login-success-ring {
          animation: ring-out 1.2s 0.2s ease-out infinite;
        }
        .login-success-glow {
          animation: glow 1.4s ease-in-out infinite alternate;
        }
        .login-success-progress {
          animation: login-progress 1.8s linear forwards;
          transform-origin: left;
        }
        .login-dot {
          animation: dots 1s infinite;
          opacity: 0.2;
        }
        .login-dot:nth-child(2) {
          animation-delay: 0.16s;
        }
        .login-dot:nth-child(3) {
          animation-delay: 0.32s;
        }
        @keyframes card-in {
          from {
            opacity: 0;
            transform: translateY(14px) scale(0.96);
          }
          to {
            opacity: 1;
            transform: none;
          }
        }
        @keyframes check-in {
          from {
            opacity: 0;
            transform: scale(0.35) rotate(-18deg);
          }
          to {
            opacity: 1;
            transform: none;
          }
        }
        @keyframes ring-out {
          from {
            opacity: 0.8;
            transform: scale(0.8);
          }
          to {
            opacity: 0;
            transform: scale(1.38);
          }
        }
        @keyframes glow {
          from {
            transform: scale(0.85);
            opacity: 0.45;
          }
          to {
            transform: scale(1.15);
            opacity: 1;
          }
        }
        @keyframes dots {
          0%,
          60%,
          100% {
            opacity: 0.2;
          }
          30% {
            opacity: 1;
          }
        }
        @keyframes login-progress {
          from {
            transform: scaleX(0);
          }
          to {
            transform: scaleX(1);
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .login-success-card,
          .login-success-check,
          .login-success-ring,
          .login-success-glow,
          .login-success-progress,
          .login-dot {
            animation: none;
          }
          .login-success-progress {
            transform: scaleX(1);
          }
        }
      `}</style>
    </main>
  );
}
