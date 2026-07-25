"use client";

import React, { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { AlertTriangle, ArrowLeft, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

const ERROR_MESSAGES: Record<string, { title: string; desc: string }> = {
  Configuration: {
    title: "Server-Konfigurationsfehler",
    desc: "Die NextAuth-Konfiguration ist fehlerhaft. Bitte prüfe die Umgebungsvariablen.",
  },
  AccessDenied: {
    title: "Zugriff verweigert",
    desc: "Du hast keine Berechtigung dich anzumelden.",
  },
  Verification: {
    title: "Verifizierung fehlgeschlagen",
    desc: "Der Verifizierungslink ist abgelaufen oder wurde bereits verwendet.",
  },
  Default: {
    title: "Authentifizierungsfehler",
    desc: "Ein unbekannter Fehler ist aufgetreten.",
  },
  OAuthSignin: {
    title: "OAuth-Anmeldung fehlgeschlagen",
    desc: "Fehler beim Starten des Discord-Anmeldevorgangs.",
  },
  OAuthCallback: {
    title: "OAuth-Callback fehlgeschlagen",
    desc: "Fehler bei der Verarbeitung der Discord-Antwort. Prüfe die Redirect URI im Discord Developer Portal.",
  },
  OAuthAccountNotLinked: {
    title: "Konto nicht verknüpft",
    desc: "Dieses Konto ist bereits mit einer anderen Anmeldemethode verknüpft.",
  },
  CredentialsSignin: {
    title: "Anmeldung fehlgeschlagen",
    desc: "Ungültige Anmeldedaten.",
  },
  SessionRequired: {
    title: "Sitzung erforderlich",
    desc: "Bitte melde dich an um fortzufahren.",
  },
};

function ErrorContent() {
  const searchParams = useSearchParams();
  const error = searchParams.get("error") || "Default";
  const errorInfo = ERROR_MESSAGES[error] || ERROR_MESSAGES.Default;

  return (
    <div className="min-h-screen bg-[#020617] flex items-center justify-center p-6">
      <div className="max-w-md w-full text-center">
        <div className="h-20 w-20 bg-red-500/10 rounded-3xl flex items-center justify-center mx-auto mb-6">
          <AlertTriangle className="h-10 w-10 text-red-500" />
        </div>
        
        <h1 className="text-3xl font-bold text-white mb-3">{errorInfo.title}</h1>
        <p className="text-slate-400 mb-2">{errorInfo.desc}</p>
        <p className="text-xs text-slate-600 mb-8 font-mono">Fehler-Code: {error}</p>

        <div className="flex flex-col gap-3">
          <Link href="/">
            <Button className="w-full gap-2 h-12 font-bold bg-red-600 hover:bg-red-500">
              <ArrowLeft className="h-4 w-4" />
              Zurück zur Startseite
            </Button>
          </Link>
          <Button 
            variant="outline" 
            className="w-full gap-2 h-12 font-bold border-slate-800"
            onClick={() => window.location.reload()}
          >
            <RefreshCw className="h-4 w-4" />
            Erneut versuchen
          </Button>
        </div>

        <div className="mt-8 p-4 bg-slate-900/50 rounded-xl border border-slate-800 text-left">
          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3">Diagnose</h3>
          <ul className="space-y-2 text-xs text-slate-400">
            <li>• Discord Developer Portal: Prüfe OAuth2 Redirect URI</li>
            <li>• Railway: Prüfe DISCORD_CLIENT_ID und DISCORD_CLIENT_SECRET</li>
            <li>• Railway: Prüfe NEXTAUTH_URL (ohne /api/auth/ Pfad)</li>
            <li>• Railway: Prüfe NEXTAUTH_SECRET (mindestens 32 Zeichen)</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

export default function AuthErrorPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#020617] flex items-center justify-center text-white">Laden...</div>}>
      <ErrorContent />
    </Suspense>
  );
}
