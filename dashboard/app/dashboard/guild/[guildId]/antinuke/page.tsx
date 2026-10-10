import { AntiNukePanel } from "@/components/dashboard/antinuke-panel";
import { NukeAlertPanel } from "@/components/dashboard/nuke-alert-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return (
    <AntiNukePanel
      guildId={params.guildId}
      reports={<NukeAlertPanel guildId={params.guildId} />}
    />
  );
}
