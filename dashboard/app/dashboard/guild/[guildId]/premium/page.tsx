import { ServerPremiumPanel } from "@/components/dashboard/server-premium-panel";

export default function ServerPremiumPage({ params }: { params: { guildId: string } }) {
  return <ServerPremiumPanel guildId={params.guildId} />;
}
