"use client";

import { usePathname } from "next/navigation";
import { CookieHinweis } from "@/components/cookie-hinweis";
import { PremiumHinweis } from "@/components/premium-hinweis";
import { SupportHinweis } from "@/components/support-hinweis";
import { ServerPremiumHinweis } from "@/components/server-premium-hinweis";

/** Keep global dialogs behind the dedicated login-success screen. */
export function GlobalPopups() {
  const pathname = usePathname();
  if (pathname.startsWith("/auth/success")) return null;
  return (
    <>
      <CookieHinweis />
      <PremiumHinweis />
      <ServerPremiumHinweis />
      <SupportHinweis />
    </>
  );
}
