"use client";

import Image from "next/image";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Bot, CalendarDays, Copy, Loader2, Server, UserRound, Users, X } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const SNOWFLAKE = /(?<!\d)(\d{17,20})(?!\d)/;

type Entity = {
  type: "user" | "server" | "unknown";
  id: string;
  name: string;
  username?: string;
  global_name?: string | null;
  image?: string | null;
  bot?: boolean;
  created_at?: string | null;
  member_count?: number;
  server_count?: number;
  owner?: { id: string; name: string; image?: string | null };
  servers?: Array<{
    id: string;
    name: string;
    image?: string | null;
    member_count?: number;
    nickname?: string | null;
    joined_at?: string | null;
  }>;
};

function Avatar({ src, name, size = 52 }: { src?: string | null; name: string; size?: number }) {
  if (src) {
    return <Image src={src} alt="" width={size} height={size} unoptimized className="shrink-0 rounded-xl object-cover" style={{ width: size, height: size }} />;
  }
  return (
    <span className="grid shrink-0 place-items-center rounded-xl bg-white/[.05] text-slate-500" style={{ width: size, height: size }}>
      <UserRound className="h-5 w-5" />
    </span>
  );
}

export function DiscordIdInspector() {
  const pathname = usePathname();
  const [entityId, setEntityId] = useState<string | null>(null);
  const [entity, setEntity] = useState<Entity | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!pathname.startsWith("/dashboard/admin")) return;

    const mark = (root: ParentNode) => {
      const candidates: HTMLElement[] = [];
      if (root instanceof HTMLElement) candidates.push(root);
      candidates.push(...Array.from(root.querySelectorAll<HTMLElement>("*")));
      for (const node of candidates) {
        if (
          !node.dataset.discordInspectorIgnore &&
          !node.dataset.discordEntityId &&
          node.children.length === 0 &&
          !node.closest("[data-discord-inspector-ignore]") &&
          !node.closest("a,input,textarea,select")
        ) {
          const text = (node.textContent || "").trim();
          const match = text.length <= 140 ? text.match(SNOWFLAKE) : null;
          if (match) {
            node.dataset.discordEntityId = match[1];
            node.classList.add("discord-id-inspectable");
            node.tabIndex = 0;
            node.setAttribute("role", "button");
            node.setAttribute("aria-label", `Discord-ID ${match[1]} anzeigen`);
          }
        }
      }
    };

    mark(document.body);
    const observer = new MutationObserver((changes) => {
      for (const change of changes) {
        for (const added of Array.from(change.addedNodes)) {
          if (added instanceof HTMLElement) mark(added);
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });

    const open = (target: EventTarget | null) => {
      const element = target instanceof Element ? target.closest<HTMLElement>("[data-discord-entity-id]") : null;
      if (!element?.dataset.discordEntityId) return false;
      setEntity(null);
      setEntityId(element.dataset.discordEntityId);
      return true;
    };
    const click = (event: MouseEvent) => {
      if (open(event.target)) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    const key = (event: KeyboardEvent) => {
      if ((event.key === "Enter" || event.key === " ") && open(event.target)) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    document.addEventListener("click", click, true);
    document.addEventListener("keydown", key, true);
    return () => {
      observer.disconnect();
      document.removeEventListener("click", click, true);
      document.removeEventListener("keydown", key, true);
    };
  }, [pathname]);

  useEffect(() => {
    if (!entityId) return;
    setLoading(true);
    api.getDiscordEntity(entityId)
      .then(setEntity)
      .catch((error: any) => {
        toast.error(error?.message || "Discord-ID konnte nicht aufgelöst werden.");
        setEntityId(null);
      })
      .finally(() => setLoading(false));
  }, [entityId]);

  if (!entityId) {
    return <style jsx global>{`.discord-id-inspectable{cursor:pointer;text-decoration:underline;text-decoration-style:dotted;text-decoration-color:rgba(96,165,250,.45);text-underline-offset:3px}.discord-id-inspectable:hover,.discord-id-inspectable:focus{color:#93c5fd!important;outline:none}`}</style>;
  }

  return (
    <>
      <style jsx global>{`.discord-id-inspectable{cursor:pointer;text-decoration:underline;text-decoration-style:dotted;text-decoration-color:rgba(96,165,250,.45);text-underline-offset:3px}.discord-id-inspectable:hover,.discord-id-inspectable:focus{color:#93c5fd!important;outline:none}`}</style>
      <div data-discord-inspector-ignore="true" className="fixed inset-0 z-[10100] grid place-items-center bg-black/75 p-4 backdrop-blur-sm" onMouseDown={(event) => { if (event.target === event.currentTarget) setEntityId(null); }}>
        <div role="dialog" aria-modal="true" aria-label="Discord-Informationen" className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-white/[.08] bg-[#202126] p-5 shadow-2xl">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold text-blue-300">Discord-Informationen</p>
              <p className="mt-0.5 text-xs tabular-nums text-slate-600">{entityId}</p>
            </div>
            <button onClick={() => setEntityId(null)} className="rounded-lg p-2 text-slate-500 hover:bg-white/[.05] hover:text-white" aria-label="Schließen"><X className="h-4 w-4" /></button>
          </div>

          {loading || !entity ? (
            <div className="grid min-h-52 place-items-center"><Loader2 className="h-5 w-5 animate-spin text-blue-300" /></div>
          ) : (
            <div className="mt-5">
              <div className="flex items-center gap-3">
                <Avatar src={entity.image} name={entity.name} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="truncate text-lg font-semibold text-white">{entity.name}</h3>
                    {entity.bot && <span className="rounded-md bg-blue-500/10 px-1.5 py-0.5 text-[9px] font-semibold text-blue-300">Bot</span>}
                  </div>
                  <p className="mt-0.5 truncate text-xs text-slate-500">
                    {entity.type === "server" ? "Discord-Server" : entity.username ? `@${entity.username}` : "Discord-Nutzer"}
                  </p>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-2">
                <Info icon={entity.type === "server" ? Server : UserRound} label="Typ" value={entity.type === "server" ? "Server" : entity.type === "user" ? "Nutzer" : "Unbekannt"} />
                <Info icon={CalendarDays} label="Erstellt" value={entity.created_at ? new Date(entity.created_at).toLocaleDateString("de-DE") : "Nicht verfügbar"} />
                {entity.type === "server" && <Info icon={Users} label="Mitglieder" value={Number(entity.member_count || 0).toLocaleString("de-DE")} />}
                {entity.type === "user" && <Info icon={Server} label="Gemeinsame Server" value={String(entity.server_count || 0)} />}
              </div>

              {entity.owner && (
                <div className="mt-4 rounded-xl border border-white/[.06] bg-black/[.1] p-3">
                  <p className="text-[10px] text-slate-600">Serverinhaber</p>
                  <div className="mt-2 flex items-center gap-2.5"><Avatar src={entity.owner.image} name={entity.owner.name} size={32} /><div className="min-w-0"><p className="truncate text-sm font-medium text-slate-200">{entity.owner.name}</p><p className="text-[10px] tabular-nums text-slate-600">{entity.owner.id}</p></div></div>
                </div>
              )}

              {entity.servers && entity.servers.length > 0 && (
                <div className="mt-4">
                  <p className="mb-2 text-[11px] font-medium text-slate-400">Server mit University Bot</p>
                  <div className="max-h-64 space-y-1.5 overflow-y-auto">
                    {entity.servers.map((server) => (
                      <div key={server.id} className="flex items-center gap-2.5 rounded-xl border border-white/[.05] bg-black/[.08] p-2.5">
                        <Avatar src={server.image} name={server.name} size={32} />
                        <div className="min-w-0 flex-1"><p className="truncate text-xs font-medium text-slate-200">{server.name}</p><p className="truncate text-[10px] text-slate-600">{server.nickname ? `Als ${server.nickname}` : "Mitglied"}{server.member_count ? ` · ${server.member_count.toLocaleString("de-DE")} Mitglieder` : ""}</p></div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <button onClick={() => { void navigator.clipboard.writeText(entityId); toast.success("Discord-ID kopiert."); }} className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-lg border border-white/[.07] bg-[#191a1f] px-3 py-2.5 text-xs font-medium text-slate-300 hover:border-white/[.12] hover:text-white"><Copy className="h-3.5 w-3.5" />ID kopieren</button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function Info({ icon: Icon, label, value }: { icon: any; label: string; value: string }) {
  return <div className="rounded-xl border border-white/[.055] bg-black/[.08] p-3"><Icon className="h-3.5 w-3.5 text-blue-300" /><p className="mt-2 text-[10px] text-slate-600">{label}</p><p className="mt-0.5 truncate text-xs font-medium text-slate-300">{value}</p></div>;
}
