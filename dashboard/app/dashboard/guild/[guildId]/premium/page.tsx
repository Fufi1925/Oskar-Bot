import { ServerPremiumPanel } from "@/components/dashboard/server-premium-panel";
export default function ServerPremiumPage({params}:{params:{guildId:string}}){return <div className="mx-auto max-w-5xl space-y-5"><ServerPremiumPanel guildId={params.guildId}/></div>}
