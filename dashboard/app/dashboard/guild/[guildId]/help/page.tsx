import { SUPPORT_INVITE } from "@/lib/legal";
import { GuildSupportPanel } from "@/components/dashboard/guild-support-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function GuildHelpPage({
  params,
}: {
  params: { guildId: string };
}) {
  return (
    <GuildSupportPanel guildId={params.guildId} supportUrl={SUPPORT_INVITE} />
  );
}
