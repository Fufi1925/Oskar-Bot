"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { SupportOperationsPanel } from "@/components/dashboard/support-operations-panel";

const SUPPORT_GUILD_ID = "1530378233579704370";

export default function OwnerOperationsPage({
  params,
}: {
  params: { guildId: string };
}) {
  const router = useRouter();
  const [allowedGuild, setAllowedGuild] = useState<string | null>(null);
  useEffect(() => {
    if (params.guildId !== SUPPORT_GUILD_ID) {
      router.replace(`/dashboard/guild/${params.guildId}`);
      return;
    }
    let active = true;
    setAllowedGuild(null);
    api
      .getSupportOperationsAccess(params.guildId)
      .then((data) => {
        if (!active) return;
        if (data.allowed === true) setAllowedGuild(params.guildId);
        else router.replace(`/dashboard/guild/${params.guildId}`);
      })
      .catch(() => {
        if (active) router.replace(`/dashboard/guild/${params.guildId}`);
      });
    return () => {
      active = false;
    };
  }, [params.guildId, router]);
  if (params.guildId !== SUPPORT_GUILD_ID || allowedGuild !== params.guildId)
    return (
      <div className="grid min-h-[420px] place-items-center">
        <Loader2 className="h-6 w-6 animate-spin text-blue-400" />
      </div>
    );
  return (
    <SupportOperationsPanel key={params.guildId} guildId={params.guildId} />
  );
}
