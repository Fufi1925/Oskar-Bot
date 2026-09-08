import { Link2 } from "lucide-react";
import { UserPullPanel } from "@/components/dashboard/user-pull-panel";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Page({ params }: { params: { guildId: string } }) {
  return (
    <div className="mx-auto max-w-6xl space-y-7 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div>
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-blue-400">
          <Link2 className="h-4 w-4" /> Verifizierung / Pull
        </div>
        <h2 className="text-2xl font-bold text-white sm:text-3xl">User Pull</h2>
        <p className="mt-2 max-w-2xl text-slate-400">
          Zukünftige, ausdrücklich autorisierte Verifizierungen sicher mit
          deinem Zielserver verbinden.
        </p>
      </div>
      <UserPullPanel guildId={params.guildId} />
    </div>
  );
}
