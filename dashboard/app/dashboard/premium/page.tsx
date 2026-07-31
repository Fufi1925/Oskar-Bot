import React from "react";
import { getServerSession } from "next-auth/next";
import { redirect } from "next/navigation";
import { Gem } from "lucide-react";

import { authOptions } from "@/lib/auth";
import { PremiumPanel } from "@/components/dashboard/premium-panel";

// The premium status is per account and changes the moment a key is
// redeemed, so a cached page would show a stale answer.
export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function PremiumPage() {
  const session = await getServerSession(authOptions);

  // No admin check on purpose: a customer who bought a key is not staff
  // and still has to be able to redeem it.
  if (!session?.user?.id) {
    redirect("/dashboard");
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Gem className="h-6 w-6 text-primary" />
          Premium
        </h2>
        <p className="text-slate-400 mt-1">
          Lizenz-Key einlösen und Premium-Status ansehen.
        </p>
      </div>

      <PremiumPanel />
    </div>
  );
}
