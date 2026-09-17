import { GuildSupportPanel } from "@/components/dashboard/guild-support-panel";

export default function GuildHelpPage({ params }: { params: { guildId: string } }) {
  return <GuildSupportPanel guildId={params.guildId} />;
}
