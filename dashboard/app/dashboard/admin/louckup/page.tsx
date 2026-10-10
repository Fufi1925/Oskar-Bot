import { getServerSession } from "next-auth/next";
import { redirect } from "next/navigation";
import { authOptions } from "@/lib/auth";
import { isOwnerId } from "@/lib/guild-auth";

export const dynamic = "force-dynamic";

export default async function LouckupPage() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id || !isOwnerId(session.user.id)) redirect("/dashboard");
  redirect("/dashboard/admin#louckup");
}
