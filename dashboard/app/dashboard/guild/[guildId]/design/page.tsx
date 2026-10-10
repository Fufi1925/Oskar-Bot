import { DesignPanel } from "@/components/dashboard/design-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return <DesignPanel guildId={params.guildId} />;
}
