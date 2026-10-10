import { BackupPanel } from "@/components/dashboard/backup-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return <BackupPanel guildId={params.guildId} />;
}
