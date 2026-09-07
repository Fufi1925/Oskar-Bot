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
          <span className="login-dot">.</span><span className="login-dot">.</span><span className="login-dot">.</span>
        </p>
        <div className="mx-auto mt-6 h-1 w-32 overflow-hidden rounded-full bg-white/5">
          <div className="login-success-progress h-full rounded-full bg-emerald-500" />
        </div>
      </section>
      <style jsx>{`
        .login-success-card { animation: card-in .42s cubic-bezier(.2,.8,.2,1) both; }
        .login-success-check { animation: check-in .55s .12s cubic-bezier(.2,1.5,.4,1) both; }
        .login-success-ring { animation: ring-out 1.2s .2s ease-out infinite; }
        .login-success-glow { animation: glow 1.4s ease-in-out infinite alternate; }
        .login-success-progress {
          animation: login-progress 1.8s linear forwards;
          transform-origin: left;
        }
        .login-dot { animation: dots 1s infinite; opacity: .2; }
        .login-dot:nth-child(2) { animation-delay: .16s; }
        .login-dot:nth-child(3) { animation-delay: .32s; }
        @keyframes card-in { from { opacity:0; transform:translateY(14px) scale(.96) } to { opacity:1; transform:none } }
        @keyframes check-in { from { opacity:0; transform:scale(.35) rotate(-18deg) } to { opacity:1; transform:none } }
        @keyframes ring-out { from { opacity:.8; transform:scale(.8) } to { opacity:0; transform:scale(1.38) } }
        @keyframes glow { from { transform:scale(.85); opacity:.45 } to { transform:scale(1.15); opacity:1 } }
        @keyframes dots { 0%,60%,100% { opacity:.2 } 30% { opacity:1 } }
        @keyframes login-progress { from { transform: scaleX(0); } to { transform: scaleX(1); } }
        @media (prefers-reduced-motion: reduce) {
          .login-success-card,.login-success-check,.login-success-ring,.login-success-glow,.login-success-progress,.login-dot { animation: none; }
          .login-success-progress { transform: scaleX(1); }
        }
      `}</style>
    </main>
  );
}
