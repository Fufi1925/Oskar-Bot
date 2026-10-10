"use client";

import { websiteLocale, useWebsiteLocale } from "@/lib/i18n/locale";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Bot, BrainCircuit, KeyRound, Loader2, RefreshCw, Search, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type Guild = {
  guild_id: string;
  name: string;
  icon: string | null;
  members: number;
  premium: boolean;
  enabled: boolean;
};

export function TicketAiAdmin() {
  const locale = useWebsiteLocale();
  const t = (de: string, en: string) => locale === "en-GB" ? en : de;
  const [guilds, setGuilds] = useState<Guild[]>([]);
  const [keyReady, setKeyReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [testQuestion, setTestQuestion] = useState("Wie viel ist 17 × 6?");
  const [testBusy, setTestBusy] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  const [testError, setTestError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const timeout = new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error("Zeitüberschreitung beim Laden der Serverliste.")), 12000);
      });
      const result = await Promise.race([api.getTicketAiAccess(), timeout]);
      setGuilds(result.guilds || []);
      setKeyReady(Boolean(result.api_key_configured));
    } catch (err: any) {
      setError(err?.message || "Serverliste konnte nicht geladen werden.");
    } finally {
      if (timer) clearTimeout(timer);
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    return guilds.filter((guild) => !query || guild.name.toLowerCase().includes(query) || guild.guild_id.includes(query));
  }, [guilds, search]);

  const runTest = async () => {
    if (!testQuestion.trim()) {
      setTestError("Bitte eine Testfrage eingeben.");
      return;
    }
    setTestBusy(true);
    setTestResult(null);
    setTestError("");
    try {
      setTestResult(await api.testTicketAi(testQuestion.trim()));
    } catch (err: any) {
      setTestError(err?.message || "Der KI-Test ist fehlgeschlagen.");
    } finally {
      setTestBusy(false);
    }
  };

  const enabled = guilds.filter((guild) => guild.enabled).length;

  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-violet-500/20 cloudtix-admin-card bg-[#131318] p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex gap-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-violet-500/12 text-violet-300"><BrainCircuit className="h-5 w-5" /></span>
            <div>
              <h2 className="text-lg font-black text-white">{t("Ticket-KI · Premium-Server", "Ticket AI · Premium servers")}</h2>
              <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-400">{t("Alle Premium-Server haben automatisch Zugriff auf die Ticket-KI. Server-Administratoren hinterlegen Wissen und aktivieren die gewünschten Ticket-Kategorien.", "Every Premium server automatically has access to Ticket AI. Server administrators add knowledge and enable the ticket categories they want.")}</p>
            </div>
          </div>
          <button type="button" onClick={load} disabled={loading} className="inline-flex items-center gap-2 rounded-xl border border-slate-700 px-3 py-2 text-xs font-bold text-slate-300 hover:bg-white/[0.04] disabled:opacity-40"><RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} /> Aktualisieren</button>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-slate-800 bg-black/20 p-4"><p className="text-[10px] font-black uppercase tracking-wider text-slate-500">Freigeschaltet</p><p className="mt-1 text-2xl font-black text-violet-300">{enabled}</p></div>
          <div className="rounded-xl border border-slate-800 bg-black/20 p-4"><p className="text-[10px] font-black uppercase tracking-wider text-slate-500">Bot-Server</p><p className="mt-1 text-2xl font-black text-white">{guilds.length}</p></div>
          <div className={cn("rounded-xl border p-4", keyReady ? "border-emerald-500/20 bg-emerald-500/[0.05]" : "border-amber-500/20 bg-amber-500/[0.05]")}><p className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-wider text-slate-500"><KeyRound className="h-3 w-3" /> Groq-Key</p><p className={cn("mt-1 text-sm font-black", keyReady ? "text-emerald-300" : "text-amber-300")}>{keyReady ? "Eingerichtet" : "Fehlt/ungültig"}</p></div>
        </div>
      </div>

      <div className="rounded-2xl border border-cyan-500/20 cloudtix-admin-card bg-[#131318] p-4 sm:p-5">
        <div className="flex items-start gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-cyan-500/10 text-cyan-300"><BrainCircuit className="h-4 w-4" /></span>
          <div>
            <h3 className="font-black text-white">Groq-KI direkt testen</h3>
            <p className="mt-1 text-xs leading-5 text-slate-400">Sendet eine Frage ohne Wissenssuche direkt an den eingerichteten Provider. Bei einem Fehler werden Modell, Finish-Grund, Tokenstatus oder HTTP-Fehler angezeigt.</p>
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <textarea value={testQuestion} onChange={(event) => setTestQuestion(event.target.value.slice(0, 1000))} rows={2} placeholder="Zum Beispiel: Wie viel ist 17 × 6?" className="min-h-20 min-w-0 flex-1 resize-y rounded-xl border border-slate-800 cloudtix-admin-field bg-[#0e0e12] px-4 py-3 text-sm text-white outline-none focus:border-cyan-500/40" />
          <button type="button" onClick={runTest} disabled={testBusy || !keyReady} className="inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-500 px-5 py-3 text-sm font-black text-black hover:bg-cyan-400 disabled:opacity-40">
            {testBusy && <Loader2 className="h-4 w-4 animate-spin" />}{testBusy ? "Teste …" : "KI testen"}
          </button>
        </div>
        {testResult && <div className="mt-3 rounded-xl border border-emerald-500/20 bg-emerald-500/[0.05] p-4"><p className="text-[10px] font-black uppercase tracking-wider text-emerald-400">Antwort erhalten · {testResult.duration_ms} ms</p><p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-white">{testResult.answer}</p><p className="mt-2 break-all text-[10px] text-slate-500">Modellreihenfolge: {(testResult.models || []).join(" → ")}</p></div>}
        {testError && <div className="mt-3 rounded-xl border border-red-500/25 bg-red-500/[0.06] p-4"><p className="text-[10px] font-black uppercase tracking-wider text-red-400">KI-Test fehlgeschlagen</p><pre className="mt-2 whitespace-pre-wrap break-words text-xs leading-5 text-red-200">{testError}</pre></div>}
      </div>

      <div className="rounded-2xl border border-slate-800 cloudtix-admin-card bg-[#131318] p-4 sm:p-5">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Servername oder Server-ID suchen" className="w-full rounded-xl border border-slate-800 cloudtix-admin-field bg-[#0e0e12] py-3 pl-10 pr-4 text-sm text-white outline-none focus:border-violet-500/40" />
        </div>

        {loading ? (
          <div className="grid min-h-52 place-items-center"><Loader2 className="h-6 w-6 animate-spin text-violet-400" /></div>
        ) : error ? (
          <div className="mt-4 rounded-xl border border-red-500/20 bg-red-500/[0.05] p-5 text-center"><p className="text-sm font-bold text-red-200">{error}</p><button onClick={load} className="mt-3 rounded-lg border border-red-400/20 px-3 py-2 text-xs font-bold text-red-200">Erneut versuchen</button></div>
        ) : (
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            {visible.map((guild) => (
              <div key={guild.guild_id} className={cn("flex items-center gap-3 rounded-xl border p-3", guild.enabled ? "border-violet-500/25 bg-violet-500/[0.05]" : "border-slate-800 cloudtix-admin-field bg-[#0e0e12]")}>
                {guild.icon ? <img src={guild.icon} alt="" className="h-10 w-10 rounded-xl object-cover" /> : <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-slate-800 text-slate-400"><Bot className="h-4 w-4" /></span>}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-bold text-white">{guild.name}</p>
                  <p className="truncate text-[10px] text-slate-600">{guild.guild_id} · {guild.members.toLocaleString(websiteLocale())} Mitglieder</p>
                  <div className="mt-1 flex gap-1.5">
                    <span className={cn("rounded px-1.5 py-0.5 text-[8px] font-black uppercase", guild.premium ? "bg-amber-400/12 text-amber-300" : "bg-slate-800 text-slate-500")}>{guild.premium ? "Premium" : "Kein Premium"}</span>
                    {guild.enabled && <span className="rounded bg-violet-500/12 px-1.5 py-0.5 text-[8px] font-black uppercase text-violet-300">KI freigeschaltet</span>}
                  </div>
                </div>
                <span className={cn("shrink-0 rounded-lg px-2 py-1 text-[10px] font-bold", guild.enabled ? "bg-violet-500/10 text-violet-300" : "bg-slate-800 text-slate-500")}>{guild.enabled ? t("Automatisch", "Automatic") : t("Premium benötigt", "Premium required")}</span>
              </div>
            ))}
            {!visible.length && <p className="col-span-full py-10 text-center text-sm text-slate-500">Kein passender Server gefunden.</p>}
          </div>
        )}
      </div>

      <div className="flex items-start gap-2 rounded-xl border border-blue-500/15 bg-blue-500/[0.04] p-4 text-xs leading-5 text-slate-400"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-blue-400" />{t("Eine zusätzliche Admin-Freigabe ist nicht erforderlich. Die bestehenden Regeln für Premium-Laufzeit und eingefrorene Einstellungen gelten weiterhin.", "No additional admin approval is required. Existing rules for Premium expiry and frozen settings still apply.")}</div>
    </div>
  );
}
