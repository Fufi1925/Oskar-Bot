"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { SupportOperationsPanel } from "@/components/dashboard/support-operations-panel";

const SUPPORT_GUILD_ID = "1530378233579704370";

export default function OwnerOperationsPage({params}:{params:{guildId:string}}) {
  const router=useRouter();
  const [allowed,setAllowed]=useState(false);
  useEffect(()=>{
    if(params.guildId!==SUPPORT_GUILD_ID){router.replace(`/dashboard/guild/${params.guildId}`);return}
    api.getSupportOperations(params.guildId).then(()=>setAllowed(true)).catch(()=>router.replace(`/dashboard/guild/${params.guildId}`));
  },[params.guildId,router]);
  if(!allowed)return <div className="grid min-h-[420px] place-items-center"><Loader2 className="h-6 w-6 animate-spin text-blue-400"/></div>;
  return <SupportOperationsPanel guildId={params.guildId}/>;
}
