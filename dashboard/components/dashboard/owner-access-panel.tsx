"use client";

import React, { useEffect, useState } from "react";
import { Crown, Loader2, Lock, ShieldPlus, Trash2, TriangleAlert } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface OwnerEntry {
  user_id: string;
  kind: "owner" | "admin";
  source: "env" | "dashboard";
  locked: boolean;
  added_by: string;
  added_at: number;
  note: string;
  username: string | null;
  avatar: string | null;
}

/**
 * Owner and admin management.
 *
 * Only real owners see this panel — it hands out unrestricted access, so a
 * team role is deliberately not enough to open it.
 */
export function OwnerAccessPanel({ currentUserId }: { currentUserId?: string }) {
  const [owners, setOwners] = useState<OwnerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [denied, setDenied] = useState(false);
  // Admins may look at the list; only owners may change it.
  const [canManage, setCanManage] = useState(false);

  const [userId, setUserId] = useState("");
  const [kind, setKind] = useState<"owner" | "admin">("admin");
  const [note, setNote] = useState("");

  const load = async () => {
    try {
      const data = await api.getOwners();
      setOwners(data.owners || []);
      setDenied(false);
    } catch (err: any) {
      if (String(err?.message || "").includes("Only owners")) {
        setDenied(true);
      } else {
        toast.error(err?.message || "Could not load the access list.");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    if (currentUserId) {
      api
        .getOwnAccess(currentUserId)
        .then((a) => setCanManage(Boolean(a?.can_manage_owners)))
        .catch(() => setCanManage(false));
    }
  }, [currentUserId]);

  const add = async () => {
    const id = userId.trim();
    if (!/^\d{15,20}$/.test(id)) return toast.error("Please enter a valid Discord user ID.");

    setBusy(true);
    try {
      await api.addOwner(id, kind, note.trim());
      toast.success(`${kind === "owner" ? "Owner" : "Admin"} added.`);
      setUserId("");
      setNote("");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Could not add this user.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (entry: OwnerEntry) => {
    setBusy(true);
    try {
      await api.removeOwner(entry.user_id);
      toast.success("Access revoked.");
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Could not revoke access.");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  if (denied) {
    return (
      <div className="bg-amber-500/10 border border-amber-500/30 rounded-3xl p-8 flex gap-4">
        <TriangleAlert className="h-6 w-6 text-amber-400 shrink-0" />
        <div>
          <h4 className="font-black text-white">Owners only</h4>
          <p className="text-sm text-amber-200/80 mt-1">
            Managing owner and admin access is restricted to bot owners. Team roles,
            even Co-Owner, cannot open this page.
          </p>
        </div>
      </div>
    );
  }

  return (
    <section className="space-y-6">
      <div className="glass border border-white/5 rounded-[2rem] p-8">
        <div className="flex items-center gap-4">
          <div className="h-12 w-12 rounded-2xl bg-amber-400/15 border border-amber-400/25 flex items-center justify-center">
            <Crown className="h-6 w-6 text-amber-400" />
          </div>
          <div>
            <h3 className="text-xl font-black text-white">Owner &amp; Admin Access</h3>
            <p className="text-sm text-slate-400 mt-1">
              {owners.length} people have unrestricted access to everything.
            </p>
          </div>
        </div>
      </div>

      {!canManage && (
        <div className="bg-white/[0.02] border border-white/5 rounded-3xl p-5 flex gap-3">
          <Lock className="h-5 w-5 text-slate-500 shrink-0" />
          <p className="text-sm text-slate-400">
            You can see this list because you are an admin, but only owners may
            change it.
          </p>
        </div>
      )}

      {/* Add */}
      {canManage && (
      <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-8">
        <h4 className="font-black text-white flex items-center gap-2 mb-6">
          <ShieldPlus className="h-5 w-5 text-primary" /> Grant full access
        </h4>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          <label className="block space-y-2">
            <span className="text-xs font-black uppercase tracking-widest text-slate-500">
              Discord user ID
            </span>
            <input
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              placeholder="123456789012345678"
              className="w-full bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </label>

          <label className="block space-y-2">
            <span className="text-xs font-black uppercase tracking-widest text-slate-500">
              Level
            </span>
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value as "owner" | "admin")}
              className="w-full bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="admin">Admin — full dashboard access</option>
              <option value="owner">Owner — full access, may add others</option>
            </select>
          </label>

          <label className="block space-y-2">
            <span className="text-xs font-black uppercase tracking-widest text-slate-500">
              Note <span className="text-slate-600">(optional)</span>
            </span>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. second account"
              className="w-full bg-white/[0.03] border border-white/5 rounded-2xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </label>
        </div>

        <div className="mt-5 flex items-start gap-3 p-4 bg-amber-500/5 border border-amber-500/20 rounded-2xl">
          <TriangleAlert className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
          <p className="text-xs text-amber-200/80 leading-relaxed">
            Both levels bypass every permission check and can act on all servers.
            For limited access use a team role instead.
          </p>
        </div>

        <button
          onClick={add}
          disabled={busy}
          className="mt-6 w-full py-4 bg-primary rounded-2xl font-black uppercase tracking-widest text-xs shadow-xl shadow-primary/20 hover:brightness-110 disabled:opacity-50"
        >
          {busy ? "Working..." : "Grant full access"}
        </button>
      </div>
      )}

      {/* List */}
      <div className="space-y-3">
        {owners.map((entry) => (
          <div
            key={entry.user_id}
            className={cn(
              "bg-[#10233f] border rounded-3xl p-6 flex items-center justify-between gap-4 flex-wrap",
              entry.kind === "owner" ? "border-amber-400/25" : "border-slate-800"
            )}
          >
            <div className="flex items-center gap-4 min-w-0">
              {entry.avatar ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={entry.avatar}
                  alt=""
                  className="h-11 w-11 rounded-2xl border border-white/10"
                />
              ) : (
                <div className="h-11 w-11 rounded-2xl bg-slate-800 flex items-center justify-center">
                  <Crown className="h-5 w-5 text-slate-500" />
                </div>
              )}
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="font-black text-white truncate">
                    {entry.username || "Unknown user"}
                  </p>
                  <span
                    className={cn(
                      "text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md border",
                      entry.kind === "owner"
                        ? "text-amber-400 border-amber-400/30 bg-amber-400/10"
                        : "text-blue-400 border-blue-400/30 bg-blue-400/10"
                    )}
                  >
                    {entry.kind}
                  </span>
                  {entry.locked && (
                    <span className="text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md bg-white/[0.04] text-slate-500 flex items-center gap-1">
                      <Lock className="h-2.5 w-2.5" />
                      env
                    </span>
                  )}
                  {entry.user_id === currentUserId && (
                    <span className="text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md bg-emerald-400/10 text-emerald-400 border border-emerald-400/20">
                      you
                    </span>
                  )}
                </div>
                <code className="text-[11px] text-slate-500 font-mono">{entry.user_id}</code>
                {entry.note && (
                  <p className="text-xs text-slate-500 mt-1 truncate">{entry.note}</p>
                )}
              </div>
            </div>

            {entry.locked ? (
              <span
                className="text-[10px] font-black uppercase tracking-widest text-slate-600"
                title="Configured through OWNER_IDS / ADMIN_IDS — change it in your environment variables"
              >
                locked
              </span>
            ) : entry.user_id === currentUserId ? (
              <span className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                cannot remove yourself
              </span>
            ) : !canManage ? null : (
              <button
                onClick={() => remove(entry)}
                disabled={busy}
                className="p-2.5 rounded-xl text-slate-500 hover:text-red-400 hover:bg-red-400/10 transition-all disabled:opacity-40"
                title="Revoke access"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            )}
          </div>
        ))}
      </div>

      <p className="text-xs text-slate-600 leading-relaxed">
        Entries marked <span className="font-bold">env</span> come from the
        <code className="mx-1 px-1.5 py-0.5 rounded bg-white/[0.04] font-mono">OWNER_IDS</code>
        and
        <code className="mx-1 px-1.5 py-0.5 rounded bg-white/[0.04] font-mono">ADMIN_IDS</code>
        variables. They would return on the next restart, so they can only be changed
        where they are configured.
      </p>
    </section>
  );
}
