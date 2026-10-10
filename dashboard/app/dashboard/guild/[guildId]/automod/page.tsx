import { AutomodPanel } from "@/components/dashboard/automod-panel";
import { AutomodStatus } from "@/components/dashboard/automod-status";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return (
    <AutomodPanel
      guildId={params.guildId}
      liveStatus={<AutomodStatus guildId={params.guildId} />}
    />
  );
}
