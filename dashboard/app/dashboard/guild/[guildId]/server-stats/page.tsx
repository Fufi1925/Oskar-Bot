import { ServerStatsPanel } from "@/components/dashboard/server-stats-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return <ServerStatsPanel guildId={params.guildId} />;
}
