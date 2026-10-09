"use client";

import { websiteLocale, useWebsiteLocale } from "@/lib/i18n/locale";
import Image from "next/image";
import { useCallback, useEffect, useState } from "react";
import { Check, Clock3, Loader2, ShoppingCart, UserRound, X } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

interface PurchaseRequest {
  id: number;
  user_id: string;
  user_name?: string;
  avatar?: string | null;
  duration_days: number;
  status: string;
  created_at?: number;
}

function AccountAvatar({ request }: { request: PurchaseRequest }) {
  useWebsiteLocale();
  if (request.avatar) {
    return (
      <Image
        src={request.avatar}
        alt=""
        width={42}
        height={42}
        unoptimized
        className="h-[42px] w-[42px] shrink-0 rounded-xl object-cover"
      />
    );
  }
  return (
    <span className="grid h-[42px] w-[42px] shrink-0 place-items-center rounded-xl bg-black/20 text-slate-500">
      <UserRound className="h-4 w-4" />
    </span>
  );
}

export function PremiumRequestsAdmin() {
  const locale = useWebsiteLocale();
  const t = (de: string, en: string) => locale === "en-GB" ? en : de;
  const [data, setData] = useState<any>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.getPremiumV2Accounts());
    } catch (error: any) {
      toast.error(error?.message || "Anfragen konnten nicht geladen werden.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const decide = async (id: number, approve: boolean) => {
    setBusy(id);
    try {
      const result = await api.decidePremiumRequest(id, approve);
      if (approve && result.dm_sent === false) toast.warning(t("Premium aktiviert. Die DM konnte nicht zugestellt werden.", "Premium activated. The DM could not be delivered."));
      else toast.success(approve ? t("Premium aktiviert und Bestätigung per DM gesendet.", "Premium activated and confirmation sent by DM.") : t("Anfrage abgelehnt.", "Request denied."));
      await load();
    } catch (error: any) {
      toast.error(error?.message || "Entscheidung fehlgeschlagen.");
    } finally {
      setBusy(null);
    }
  };

  const pending: PurchaseRequest[] = (data?.requests || []).filter(
    (request: PurchaseRequest) => request.status === "pending",
  );

  return (
    <section className="rounded-xl border border-white/[.06] bg-[#202126] p-4 sm:p-5">
      <div className="flex items-center gap-3">
        <span className="grid h-9 w-9 place-items-center rounded-lg bg-amber-400/10">
          <ShoppingCart className="h-4 w-4 text-amber-300" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-white">Kaufanfragen</h3>
            {pending.length > 0 && (
              <span className="rounded-md bg-amber-400/10 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300">
                {pending.length} offen
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs text-slate-500">
            Bestätigte Nutzer erhalten drei feste Serverplätze.
          </p>
        </div>
      </div>

      {!data ? (
        <Loader2 className="mx-auto mt-6 h-5 w-5 animate-spin text-amber-300" />
      ) : pending.length ? (
        <div className="mt-4 divide-y divide-white/[.055] border-t border-white/[.055]">
          {pending.map((request) => (
            <div key={request.id} className="flex flex-col gap-3 py-3.5 sm:flex-row sm:items-center">
              <div className="flex min-w-0 flex-1 items-center gap-3">
                <AccountAvatar request={request} />
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-white">
                    {request.user_name || "Unbekannter Nutzer"}
                  </p>
                  <p className="mt-0.5 truncate text-[11px] tabular-nums text-slate-500">
                    {request.user_id}
                  </p>
                  <p className="mt-1 flex items-center gap-1.5 text-[11px] text-slate-600">
                    <Clock3 className="h-3 w-3" />
                    {request.duration_days === 0 ? "Lifetime" : `${request.duration_days} ${t("Tage", "days")}`} · {t("Anfrage", "Request")} #{request.id}
                    {request.created_at
                      ? ` · ${new Date(request.created_at * 1000).toLocaleDateString(websiteLocale())}`
                      : ""}
                  </p>
                </div>
              </div>
              <div className="flex gap-2 sm:shrink-0">
                <button
                  disabled={busy === request.id}
                  onClick={() => decide(request.id, true)}
                  className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-emerald-500/15 px-3 py-2 text-xs font-semibold text-emerald-300 transition-colors hover:bg-emerald-500/25 disabled:opacity-40 sm:flex-none"
                >
                  <Check className="h-3.5 w-3.5" /> Annehmen
                </button>
                <button
                  disabled={busy === request.id}
                  onClick={() => decide(request.id, false)}
                  className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-red-500/20 px-3 py-2 text-xs font-semibold text-red-300 transition-colors hover:bg-red-500/10 disabled:opacity-40 sm:flex-none"
                >
                  <X className="h-3.5 w-3.5" /> Ablehnen
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-4 border-t border-white/[.055] pt-4 text-sm text-slate-500">
          Keine offenen Kaufanfragen.
        </p>
      )}

      {data?.accounts?.length > 0 && (
        <div className="mt-5 border-t border-white/[.055] pt-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <p className="text-xs font-semibold text-slate-300">Premium-Konten und Serverplätze</p>
            <span className="text-[11px] text-slate-600">{data.accounts.length} Konten</span>
          </div>
          <div className="grid gap-2.5 lg:grid-cols-2">
            {data.accounts.map((account: any) => (
              <article key={account.user_id} className="rounded-xl border border-white/[.055] bg-black/[.09] p-3.5">
                <div className="flex items-center gap-3">
                  {account.avatar ? (
                    <Image src={account.avatar} alt="" width={36} height={36} unoptimized className="h-9 w-9 rounded-lg object-cover" />
                  ) : (
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-black/20"><UserRound className="h-4 w-4 text-slate-600" /></span>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-white">{account.user_name || account.user_id}</p>
                    <p className="truncate text-[10px] tabular-nums text-slate-600">{account.user_id}</p>
                  </div>
                  <span className={account.premium ? "text-[11px] font-semibold text-emerald-300" : "text-[11px] font-semibold text-slate-500"}>
                    {account.premium ? "Aktiv" : "Abgelaufen"}
                  </span>
                </div>
                <p className="mt-2.5 text-[11px] text-slate-500">
                  Laufzeit bis {account.expires_at ? new Date(account.expires_at * 1000).toLocaleDateString(websiteLocale()) : "–"}
                </p>
                <div className="mt-2 grid grid-cols-3 gap-1.5">
                  {[1, 2, 3].map((number) => {
                    const slot = (account.slots || []).find((item: any) => item.slot_no === number);
                    return (
                      <div key={number} className="min-w-0 rounded-lg bg-black/15 px-2 py-1.5">
                        <p className="text-[9px] text-slate-600">Platz {number}</p>
                        <p className={slot ? "truncate text-[10px] text-violet-300" : "truncate text-[10px] text-slate-600"}>{slot?.guild_name || "frei"}</p>
                      </div>
                    );
                  })}
                </div>
              </article>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
