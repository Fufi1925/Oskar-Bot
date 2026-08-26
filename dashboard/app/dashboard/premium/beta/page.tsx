import React from "react";
import Link from "next/link";
import { getServerSession } from "next-auth/next";
import { redirect } from "next/navigation";
import { ArrowLeft, Sparkles } from "lucide-react";

import { authOptions } from "@/lib/auth";
import { BetaForm } from "@/components/dashboard/beta-form";
import { Reveal } from "@/components/ui/reveal";

// Der Stand haengt am angemeldeten Konto und aendert sich, sobald ein
// Antrag entschieden wird -- eine zwischengespeicherte Seite zeigte
// eine veraltete Antwort.
export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function BetaPage() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) {
    redirect("/dashboard");
  }

  return (
    <Reveal className="max-w-3xl mx-auto space-y-6">
      <div>
        <Link
          href="/dashboard/premium"
          className="inline-flex items-center gap-1.5 text-sm text-slate-500 transition hover:text-slate-300"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Zurück zu Premium
        </Link>
        <h2 className="mt-3 flex items-center gap-2 text-2xl font-bold text-white">
          <Sparkles className="h-6 w-6 text-amber-400" />
          Beta-Bewerbung
        </h2>
        <p className="mt-1 text-slate-400">
          F&uuml;nf Fragen. Wir melden uns in 1&ndash;7 Tagen per Discord.
        </p>
      </div>

      <BetaForm />
    </Reveal>
  );
}
