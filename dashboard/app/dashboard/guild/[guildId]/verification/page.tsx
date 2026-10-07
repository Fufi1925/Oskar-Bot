import { VerifyPanel } from "@/components/dashboard/verify-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return <div className="mx-auto max-w-7xl"><VerifyPanel guildId={params.guildId} /></div>;
}
