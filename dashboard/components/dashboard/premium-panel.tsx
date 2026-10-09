"use client";

import { useWebsiteLocale } from "@/lib/i18n/locale";
import { WebsiteSelect } from "@/components/ui/website-select";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, CheckCircle2, Crown, ExternalLink, Loader2, Server, ShoppingCart, User, X } from "lucide-react";
import { useSession } from "next-auth/react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type Billing = { enabled: boolean; mode: string; has_customer: boolean; plans: { id: string; amount: number; interval: string | null }[]; subscriptions: { plan: string; status: string; cancel_at_period_end: number; period_end: number }[] };

export function PremiumPanel() {
  const locale = useWebsiteLocale();
  const language = locale.startsWith("de") ? "de" : "en";
  const t = useCallback((de: string, en: string) => language === "de" ? de : en, [language]);
  const { data: session } = useSession();
  const userId = session?.user?.id || "";
  const [status, setStatus] = useState<any>(null);
  const [billing, setBilling] = useState<Billing | null>(null);
  const [servers, setServers] = useState<any[]>([]);
  const [plan, setPlan] = useState("monthly");
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [successGuild, setSuccessGuild] = useState("");
  const [paymentState, setPaymentState] = useState("");
  const fmt = (value?: number | null) => value ? new Date(value * 1000).toLocaleString(locale) : "–";
  const price = (amount: number) => new Intl.NumberFormat(locale, { style: "currency", currency: "EUR" }).format(amount / 100);

  const errorText = (error: any) => {
    const messages: Record<string, [string, string]> = {
      billing_unavailable: ["Zahlungen sind noch nicht eingerichtet.", "Payments have not been configured yet."],
      billing_configuration: ["Die Zahlungseinstellungen müssen vom Team geprüft werden.", "The team needs to check the payment configuration."],
      billing_already_active: ["Du hast bereits Premium oder ein laufendes Abo. Öffne die Aboverwaltung.", "You already have Premium or a subscription. Open billing management."],
      billing_checkout_pending: ["Eine andere Zahlung ist noch offen. Nutze das zuvor gewählte Paket oder warte eine Stunde.", "Another checkout is still open. Use the previous plan or wait one hour."],
      billing_provider: ["Stripe ist gerade nicht erreichbar. Versuche es erneut.", "Stripe is currently unavailable. Please try again."],
    };
    const message = messages[error?.message];
    return message ? t(...message) : t("Die Anfrage konnte nicht abgeschlossen werden.", "The request could not be completed.");
  };

  const load = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    try {
      const [mine, choices, payment] = await Promise.all([api.getMyPremium(userId), api.premiumCodeServers(), api.getPremiumBilling()]);
      setStatus(mine.premium); setServers(choices.servers || []); setBilling(payment); setLoadError(false);
    } catch { setLoadError(true); }
    finally { setLoading(false); }
  }, [userId]);
  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!userId) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("payment") === "cancelled") { setPaymentState("cancelled"); return; }
    const checkoutId = params.get("session_id");
    if (params.get("payment") !== "success" || !checkoutId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    setPaymentState("pending");
    const poll = async () => {
      try {
        const payment = await api.getPremiumCheckoutStatus(checkoutId);
        if (cancelled) return;
        if (payment.fulfilled && payment.payment_status === "paid") {
          setPaymentState("confirmed"); await load(); return;
        }
      } catch { if (cancelled) return; }
      if (++attempts < 15) timer = setTimeout(poll, 3000);
      else setPaymentState("waiting");
    };
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [userId, load]);

  const used = status?.slots || [];
  const available = useMemo(() => servers.filter(server => !used.some((slot: any) => String(slot.guild_id) === server.id)), [servers, used]);
  const activeSubscription = billing?.subscriptions.find(sub => !["canceled", "incomplete_expired"].includes(sub.status));
  const redirect = async (portal = false) => {
    setBusy(true);
    try {
      const result = portal ? await api.openPremiumPortal() : await api.createPremiumCheckout(plan, language);
      const target = new URL(result.url);
      if (target.protocol !== "https:" || target.hostname !== (portal ? "billing.stripe.com" : "checkout.stripe.com")) throw new Error("billing_provider");
      window.location.assign(result.url);
    } catch (error) { toast.error(errorText(error)); setBusy(false); }
  };
  const assign = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      const name = servers.find(server => server.id === selected)?.name || selected;
      await api.assignPremiumSlot(selected); setConfirmOpen(false); setSuccessGuild(name); setSelected(""); await load();
    } catch (error) { toast.error(errorText(error)); }
    finally { setBusy(false); }
  };

  if (loading) return <div className="grid min-h-60 place-items-center"><Loader2 className="h-7 w-7 animate-spin text-amber-400" aria-label={t("Wird geladen", "Loading")} /></div>;
  if (loadError) return <div className="rounded-2xl border border-red-500/20 p-5"><p className="text-slate-300">{t("Premium konnte nicht geladen werden.", "Premium could not be loaded.")}</p><button onClick={() => void load()} className="mt-3 text-violet-300">{t("Erneut versuchen", "Try again")}</button></div>;
  const paymentMessages: Record<string, string> = {
    pending: t("Deine Zahlung wird bestätigt …", "Your payment is being confirmed …"),
    waiting: t("Die Bestätigung steht noch aus. Premium wird nach bestätigtem Zahlungseingang automatisch aktiviert. Lade später erneut.", "Confirmation is still pending. Premium activates automatically after payment is confirmed. Refresh again later."),
    confirmed: t("Zahlung bestätigt. Dein Premium ist aktiv!", "Payment confirmed. Your Premium is active!"),
    cancelled: t("Du hast den Bezahlvorgang abgebrochen. Du kannst es jederzeit erneut versuchen.", "You cancelled checkout. You can try again at any time."),
  };

  return <div className="space-y-5" data-no-translate>
    {paymentState && <div role="status" className={cn("rounded-2xl border p-4 text-sm", paymentState === "confirmed" ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-200" : "border-amber-400/20 bg-amber-400/5 text-amber-100")}>{paymentMessages[paymentState]}</div>}
    <section className="rounded-3xl border border-amber-400/20 bg-gradient-to-br from-amber-500/[0.1] to-[#0e0e12] p-5 sm:p-6">
      <div className="flex items-center gap-3"><span className="grid h-12 w-12 place-items-center rounded-2xl bg-amber-400/15"><User className="h-5 w-5 text-amber-300" /></span><div className="min-w-0"><p className="text-xs font-bold uppercase tracking-wider text-amber-300">{t("Discord-Konto", "Discord account")}</p><h2 className="truncate text-xl font-black text-white">{session?.user?.name || userId}</h2><p className="text-xs text-slate-500">{userId}</p></div></div>
      <div className="mt-5 grid gap-3 sm:grid-cols-3"><div className="rounded-xl border border-white/5 bg-black/20 p-4"><p className="text-[10px] uppercase text-slate-500">{t("Kontostatus", "Account status")}</p><p className={cn("mt-1 font-black", status?.premium ? "text-emerald-300" : "text-slate-400")}>{status?.premium ? t("Premium aktiv", "Premium active") : t("Kein Premium", "No Premium")}</p></div><div className="rounded-xl border border-white/5 bg-black/20 p-4"><p className="text-[10px] uppercase text-slate-500">{t("Laufzeit", "Access period")}</p><p className="mt-1 font-black text-white">{status?.lifetime ? t("Lebenslang", "Lifetime") : fmt(status?.expires_at)}</p></div><div className="rounded-xl border border-white/5 bg-black/20 p-4"><p className="text-[10px] uppercase text-slate-500">{t("Serverplätze", "Server slots")}</p><p className="mt-1 font-black text-white">{used.length} / 3 {t("belegt", "assigned")}</p></div></div>
    </section>

    {billing?.has_customer && <section className="rounded-2xl border border-slate-800 bg-[#131318] p-5"><h3 className="font-black text-white">{t("Zahlungen und Abos", "Payments and subscriptions")}</h3><p className="mt-1 text-sm text-slate-400">{t("Rechnungen, Zahlungsmethoden und Kündigungen sicher bei Stripe verwalten.", "Manage invoices, payment methods and cancellations securely with Stripe.")}</p>{activeSubscription && <p className="mt-3 text-sm text-amber-200">{activeSubscription.cancel_at_period_end ? t("Dein Abo endet zum Ende des bezahlten Zeitraums:", "Your subscription ends at the end of the paid period:") : t("Nächster Abrechnungszeitpunkt:", "Next billing date:")} {fmt(activeSubscription.period_end)}</p>}<button disabled={busy} onClick={() => void redirect(true)} className="mt-4 flex items-center gap-2 rounded-xl border border-violet-400/30 px-4 py-3 text-sm font-bold text-violet-200 disabled:opacity-40"><ExternalLink className="h-4 w-4" />{t("Aboverwaltung öffnen", "Open billing management")}</button></section>}

    {!status?.premium && !activeSubscription && <section className="rounded-2xl border border-slate-800 bg-[#131318] p-5"><div className="flex items-center gap-3"><ShoppingCart className="text-amber-400"/><div><h3 className="font-black text-white">{t("Premium kaufen", "Buy Premium")}</h3><p className="text-xs text-slate-400">{t("Drei feste Premium-Serverplätze und alle Premium-Funktionen, einschließlich Ticket-KI.", "Three fixed Premium server slots and all Premium features, including Ticket AI.")}</p></div></div>
      {billing?.mode === "test" && <p className="mt-3 rounded-lg bg-amber-400/10 p-3 text-xs text-amber-200">{t("Testmodus: Hier werden keine echten Zahlungen durchgeführt.", "Test mode: No real payments are collected here.")}</p>}
      <div className="mt-4 grid gap-2 sm:grid-cols-3">{billing?.plans.map(item => <button key={item.id} onClick={() => setPlan(item.id)} aria-pressed={plan === item.id} className={cn("rounded-xl border p-4 text-left transition-colors", plan === item.id ? "border-amber-400/40 bg-amber-400/10" : "border-slate-800 hover:border-slate-600")}><p className="text-xs text-slate-400">{item.id === "monthly" ? t("Monat", "Month") : item.id === "yearly" ? t("Jahr", "Year") : "Lifetime"}</p><p className="mt-2 text-2xl font-black text-white">{price(item.amount)}</p><p className="mt-1 text-xs text-slate-400">{item.interval ? t("Automatische Verlängerung", "Renews automatically") : t("Einmalige Zahlung", "One-time payment")}</p></button>)}</div>
      <p className="mt-4 text-xs leading-5 text-slate-400">{plan === "lifetime" ? t("Einmal zahlen, Premium dauerhaft nutzen. Kein Abo.", "Pay once for permanent Premium access. No subscription.") : t("Dein Abo verlängert sich automatisch monatlich oder jährlich. Du kannst es im Kundenportal zum Ende des bezahlten Zeitraums kündigen.", "Your subscription renews automatically monthly or yearly. Cancel in the customer portal at the end of the paid period.")}</p>
      {!billing?.enabled && <p className="mt-3 text-xs text-amber-200">{t("Zahlungen werden gerade eingerichtet. Bitte später erneut vorbeischauen.", "Payments are being set up. Please check back later.")}</p>}
      <button disabled={busy || !billing?.enabled} onClick={() => void redirect()} className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-amber-400 py-3 text-sm font-black text-black disabled:opacity-40">{busy && <Loader2 className="h-4 w-4 animate-spin"/>}{t("Weiter zu Stripe", "Continue to Stripe")}</button></section>}

    <section className="rounded-2xl border border-violet-500/20 bg-[#131318] p-5"><div className="flex items-center gap-3"><Crown className="text-violet-300"/><div><h3 className="font-black text-white">{t("Deine drei Premium-Server", "Your three Premium servers")}</h3><p className="text-xs text-slate-400">{t("Premium gilt für die hier fest zugewiesenen Server und deren berechtigte Dashboard-Nutzer.", "Premium applies to the servers assigned here and their authorized dashboard users.")}</p></div></div><div className="mt-4 grid gap-3 sm:grid-cols-3">{[1,2,3].map(slot => {const value = used.find((item: any) => item.slot_no === slot); const guild = servers.find(s => s.id === String(value?.guild_id)); return <div key={slot} className={cn("rounded-xl border p-4", value ? "border-violet-500/25 bg-violet-500/[0.06]" : "border-dashed border-slate-700")}><p className="text-[10px] font-black uppercase text-slate-500">{t("Platz", "Slot")} {slot}</p>{value ? <><p className="mt-2 truncate font-bold text-white">{guild?.name || value.guild_id}</p><p className="mt-1 flex items-center gap-1 text-[11px] text-emerald-300"><Check className="h-3 w-3"/>{t("Fest zugewiesen", "Permanently assigned")}</p></> : <p className="mt-2 text-sm text-slate-500">{t("Noch frei", "Available")}</p>}</div>;})}</div>
      {status?.premium && used.length < 3 && <div className="mt-4 flex flex-col gap-2 sm:flex-row"><WebsiteSelect value={selected} onChange={e => setSelected(e.target.value)} aria-label={t("Server auswählen", "Choose a server")} className="min-w-0 flex-1 rounded-xl border border-slate-700 bg-[#09090c] px-4 py-3 text-sm text-white"><option value="">{t("Server auswählen …", "Choose a server …")}</option>{available.map(server => <option key={server.id} value={server.id}>{server.name}</option>)}</WebsiteSelect><button disabled={busy || !selected} onClick={() => setConfirmOpen(true)} className="rounded-xl bg-violet-500 px-5 py-3 text-sm font-black text-white disabled:opacity-40"><Server className="mr-2 inline h-4 w-4"/>{t("Premium fest einlösen", "Assign Premium slot")}</button></div>}
    </section>

    {confirmOpen && <div role="dialog" aria-modal="true" aria-labelledby="premium-confirm-title" className="fixed inset-0 z-[10020] grid place-items-center bg-black/80 p-4 backdrop-blur-sm"><div className="relative w-full max-w-md rounded-3xl border border-violet-400/30 bg-[#131318] p-6 shadow-2xl"><button onClick={() => setConfirmOpen(false)} aria-label={t("Schließen", "Close")} className="absolute right-4 top-4 text-slate-500 hover:text-white"><X className="h-5 w-5"/></button><AlertTriangle className="h-6 w-6 text-amber-300"/><h3 id="premium-confirm-title" className="mt-4 text-xl font-black text-white">{t("Premiumplatz fest zuweisen?", "Assign a fixed Premium slot?")}</h3><p className="mt-2 text-sm leading-6 text-slate-400"><strong className="text-white">{servers.find(server => server.id === selected)?.name}</strong> {t("belegt danach einen deiner drei Plätze. Während der aktuellen Laufzeit kannst du diesen Server nicht austauschen.", "will take one of your three slots. You cannot replace this server during the current access period.")}</p><p className="mt-4 text-xs text-amber-100">{t("Bei Lifetime bleibt die Zuweisung dauerhaft. Owner-only-Funktionen bleiben geschützt.", "Lifetime assignments are permanent. Owner-only features remain protected.")}</p><div className="mt-5 grid grid-cols-2 gap-2"><button onClick={() => setConfirmOpen(false)} className="rounded-xl border border-slate-700 py-3 text-sm font-bold text-slate-300">{t("Abbrechen", "Cancel")}</button><button onClick={() => void assign()} disabled={busy} className="rounded-xl bg-violet-500 py-3 text-sm font-black text-white disabled:opacity-50">{busy ? t("Wird zugewiesen …", "Assigning …") : t("Fest zuweisen", "Assign slot")}</button></div></div></div>}
    {successGuild && <div role="dialog" aria-modal="true" aria-labelledby="premium-success-title" className="fixed inset-0 z-[10020] grid place-items-center bg-black/80 p-4 backdrop-blur-sm"><div className="w-full max-w-md rounded-3xl border border-emerald-400/25 bg-[#131318] p-6 text-center shadow-2xl"><CheckCircle2 className="mx-auto h-7 w-7 text-emerald-300"/><h3 id="premium-success-title" className="mt-4 text-xl font-black text-white">{t("Server-Premium ist aktiv", "Server Premium is active")}</h3><p className="mt-2 text-sm leading-6 text-slate-400"><strong className="text-white">{successGuild}</strong> {t("hat jetzt einen festen Premiumplatz. Alle Premiumbereiche dieses Servers sind freigeschaltet.", "now has a fixed Premium slot. All Premium features are unlocked on this server.")}</p><button onClick={() => setSuccessGuild("")} className="mt-5 w-full rounded-xl bg-emerald-500 py-3 text-sm font-black text-white">{t("Verstanden", "Got it")}</button></div></div>}
  </div>;
}
