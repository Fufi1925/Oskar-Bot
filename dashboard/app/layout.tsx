/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║                                                                  ║
 * ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
 * ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
 * ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
 * ║                                                                  ║
 * ║           © 2026 University Bot Devs — All Rights Reserved               ║
 * ║                                                                  ║
 * ║   discord  ──  https://discord.gg/MG3rYnUZJV                      ║
 * ║   youtube  ──  https://youtube.com/@University BotDevs                   ║
 * ║   github   ──  https://github.com/University Bot                        ║
 * ║                                                                  ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

import type { Metadata, Viewport } from "next";
import "./globals.css";

import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/components/auth-provider";
import { LanguageProvider } from "@/lib/i18n/LanguageContext";
import { BorderGlowProvider } from "@/components/ui/border-glow";

const brandName = process.env.NEXT_PUBLIC_BRAND_NAME || "University Bot";

export const metadata: Metadata = {
  title: `${brandName} - Ultimate Discord Bot`,
  description: "Advanced Discord community management and security.",
};

/**
 * Without this a phone renders the page at roughly 980px and then zooms
 * out to fit, which is why everything was tiny and every tap landed
 * next to the thing it was aimed at. Next only emits the tag when a
 * viewport export exists.
 *
 * maximumScale is deliberately not set: capping zoom locks out anybody
 * who needs to enlarge text.
 */
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0b1f3a",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="font-sans antialiased text-slate-200">
        <AuthProvider>
          <LanguageProvider>{children}</LanguageProvider>
          <Toaster />
        </AuthProvider>
        {/* One pointer listener for every card on the page. Mounted here
            rather than per card: 132 listeners and 132 rAF loops for
            one cursor is work nobody sees. Renders no markup. */}
        <BorderGlowProvider />
      </body>
    </html>
  );
}
