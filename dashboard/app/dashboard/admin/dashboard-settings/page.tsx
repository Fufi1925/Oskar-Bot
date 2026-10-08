import { getServerSession } from "next-auth/next";
import { redirect } from "next/navigation";
import { authOptions } from "@/lib/auth";
import { isOwnerId } from "@/lib/guild-auth";
import { DashboardSettingsPanel } from "@/components/dashboard/dashboard-settings-panel";

export const dynamic = "force-dynamic";
export default async function Page() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id || !isOwnerId(session.user.id)) redirect("/dashboard");
  return <DashboardSettingsPanel currentUserId={session.user.id} />;
}
