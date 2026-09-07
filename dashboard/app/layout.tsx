/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║                                                                  ║
 * ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
 * ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
 * ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
 * ║                                                                  ║
 * ║           © 2026 University Bot Devs — All Rights Reserved               ║
 * ║                                                                  ║
 * ║   discord  ──  https://discord.gg/F3TedBAVZT                      ║
 * ║   youtube  ──  https://youtube.com/@University BotDevs                   ║
 * ║   github   ──  https://github.com/University Bot                        ║
 * ║                                                                  ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

import type { Metadata, Viewport } from "next";
import "./globals.css";

import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/components/auth-provider";
import { GlobalPopups } from "@/components/global-popups";
import { LanguageProvider } from "@/lib/i18n/LanguageContext";

const brandName = process.env.NEXT_PUBLIC_BRAND_NAME || "University Bot";

export const metadata: Metadata = {
  title: `${brandName} - Ultimate Discord Bot`,
  description: "Advanced Discord community management and security.",
  icons: {
    icon: [
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    shortcut: "/favicon.ico",
    apple: "/apple-touch-icon.png",
  },
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
  themeColor: "#0a0a0c",
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
          {/* Globale Hinweise bleiben während der wichtigen
              Login-Erfolgsanzeige geschlossen. Erst nach der Weiterleitung
              ins Dashboard dürfen Cookie-, Premium- und Supportdialoge
              erscheinen. Innerhalb des AuthProviders, weil sie die Sitzung
              des angemeldeten Discord-Kontos benötigen. */}
          <GlobalPopups />
        </AuthProvider>
      </body>
    </html>
  );
}
