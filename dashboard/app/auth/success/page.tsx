"use client";

import React, { useEffect } from "react";
import { Check } from "lucide-react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";

/**
 * Deliberate post-login step. It is a real route rather than a toast on the
 * dashboard so no cookie, premium or support dialog can cover the successful
 * sign-in confirmation before the user has seen it.
 */
export default function LoginSuccessPage() {
  const router = useRouter();
  const { status } = useSession();

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/");
      return;
    }
    if (status !== "authenticated") return;

    const requested = new URLSearchParams(window.location.search).get("next") || "/dashboard";
    const destination = requested.startsWith("/") && !requested.startsWith("//")
      ? requested
      : "/dashboard";
    const timer = window.setTimeout(() => router.replace(destination), 1800);
    return () => window.clearTimeout(timer);
  }, [router, status]);

  return (
    <main className="fixed inset-0 z-[10000] grid min-h-screen place-items-center bg-[#070708] px-5">
      <section
        role="status"
        aria-live="polite"
        className="w-full max-w-sm rounded-lg border border-white/[0.03] bg-[#141415] px-6 py-8 text-center shadow-2xl shadow-black/60 sm:px-10"
      >
        <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-emerald-500">
          <Check className="h-9 w-9 text-white" strokeWidth={2.5} />
        </div>
        <h1 className="mt-5 text-2xl font-black text-white">Erfolgreich!</h1>
        <p className="mt-2 text-sm text-slate-300">Login erfolgreich! Weiterleitung...</p>
        <div className="mx-auto mt-6 h-1 w-32 overflow-hidden rounded-full bg-white/5">
          <div className="login-success-progress h-full rounded-full bg-emerald-500" />
        </div>
      </section>
      <style jsx>{`
        .login-success-progress {
          animation: login-progress 1.8s linear forwards;
          transform-origin: left;
        }
        @keyframes login-progress {
          from { transform: scaleX(0); }
          to { transform: scaleX(1); }
        }
        @media (prefers-reduced-motion: reduce) {
          .login-success-progress { animation: none; transform: scaleX(1); }
        }
      `}</style>
    </main>
  );
}
