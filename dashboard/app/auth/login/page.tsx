"use client";

import { Suspense, useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { signIn, useSession } from "next-auth/react";
import { Loader2 } from "lucide-react";
import { loginCallbackUrl, loginDestination } from "@/lib/auth-navigation";

function LoginRedirect() {
  const router = useRouter();
  const params = useSearchParams();
  const { data: session, status } = useSession();
  const started = useRef(false);
  const requested = params.get("next") || params.get("callbackUrl");

  useEffect(() => {
    if (status === "loading" || started.current) return;
    let destination = loginDestination(requested, "/dashboard", window.location.origin);
    if (!destination.includes("#")) destination += window.location.hash;
    started.current = true;
    if (status === "authenticated" && session?.user?.id && session.accessToken && !session.revoked) {
      router.replace(destination);
      return;
    }
    void signIn("discord", { callbackUrl: loginCallbackUrl(destination, window.location.origin) }).catch(() => {
      router.replace(`/auth/error?error=OAuthSignin&next=${encodeURIComponent(destination)}`);
    });
  }, [requested, router, session, status]);

  return (
    <main className="grid min-h-screen place-items-center bg-[#09090b] px-5 text-white">
      <div role="status" aria-live="polite" className="flex items-center gap-3 text-sm">
        <Loader2 className="h-5 w-5 animate-spin text-blue-400" />
        Discord-Anmeldung wird geöffnet …
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-[#09090b]" />}>
      <LoginRedirect />
    </Suspense>
  );
}
