import { getServerSession } from "next-auth/next";
import { redirect } from "next/navigation";
import { authOptions } from "@/lib/auth";
import { isOwnerId } from "@/lib/guild-auth";
import { OwnerLouckupPanel } from "@/components/dashboard/owner-louckup-panel";

export const dynamic = "force-dynamic";

export default async function LouckupPage() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id || !isOwnerId(session.user.id)) redirect("/dashboard");
  return <div className="mx-auto max-w-6xl px-4 py-8 sm:px-8"><OwnerLouckupPanel /></div>;
}
