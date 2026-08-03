"use client";

/**
 * Speedrun (Beta) — einen Server in einem Durchlauf aufsetzen.
 *
 * Vier Schritte, in dieser Reihenfolge, weil jeder auf dem vorigen
 * aufbaut:
 *
 *   1. Voraussetzungen   sind beide Bots da und dürfen sie überhaupt?
 *   2. Vorlage           welches Template gebaut wird
 *   3. Umfang            was der University Bot danach einrichtet
 *   4. Lauf              das Terminal, Zeile für Zeile, beide Bots
 *
 * Zwei Dinge, die hier bewusst so sind:
 *
 *   * **Der Browser entscheidet nichts.** Ob ein Template freigegeben
 *     ist, ob jemand Premium hat, ob beide Bots auf dem Server sind —
 *     das beantwortet der Bot. Hier wird es nur angezeigt. Eine Sperre,
 *     die nur im Browser sitzt, ist keine.
 *
 *   * **Der Fortschritt wird abgefragt, nicht gestreamt.** Ein Bau
 *     dauert Minuten und läuft im anderen Bot; eine offene Verbindung
 *     über einen Proxy und zwei Dienste hinweg reißt zuverlässiger ab,
 *     als sie hält. Zwei Zähler (`since`, `sinceMain`) holen jeweils nur
 *     die neuen Zeilen — sonst wächst jede Abfrage mit der Loglänge.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  Circle,
  Gauge,
  Loader2,
  Lock,
  RefreshCw,
  Rocket,
  Sparkles,
  Terminal,
  X,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { InlineToggle } from "@/components/dashboard/form-elements";

/* ── Typen ──────────────────────────────────────────────────────── */

interface LogLine {
  text: string;
  source: "template" | "main";
  level: string;
  at: number;
}

interface StepSpec {
  key: string;
  label: string;
  description: string;
  default: boolean;
}

/** Wie oft der Fortschritt abgefragt wird, während etwas läuft. */
const POLL_MS = 1500;

const CARD =
  "bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 border-glow-card";

/* ── Kleinteile ─────────────────────────────────────────────────── */

function StepDots({ current }: { current: number }) {
  const names = ["Voraussetzungen", "Vorlage", "Umfang", "Lauf"];
  return (
    <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
      {names.map((name, index) => {
        const done = index < current;
        const active = index === current;
        return (
          <React.Fragment key={name}>
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "h-6 w-6 rounded-full grid place-items-center text-[10px] font-black shrink-0",
                  done && "bg-emerald-500/20 text-emerald-300",
                  active && "bg-primary text-white",
                  !done && !active && "bg-slate-800 text-slate-500"
                )}
              >
                {done ? <Check className="h-3 w-3" /> : index + 1}
              </span>
              <span
                className={cn(
                  "text-[11px] font-black uppercase tracking-wider hidden sm:inline",
                  active ? "text-white" : "text-slate-500"
                )}
              >
                {name}
              </span>
            </div>
            {index < names.length - 1 && (
              <span className="h-px w-4 sm:w-8 bg-slate-800 shrink-0" />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

function Requirement({
  ok,
  label,
  detail,
  action,
}: {
  ok: boolean;
  label: string;
  detail?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 py-2.5">
      {ok ? (
        <CheckCircle2 className="h-4.5 w-4.5 text-emerald-400 shrink-0 mt-0.5" />
      ) : (
        <XCircle className="h-4.5 w-4.5 text-red-400 shrink-0 mt-0.5" />
      )}
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            "text-sm font-bold",
            ok ? "text-slate-300" : "text-white"
          )}
        >
          {label}
        </p>
        {detail && (
          <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">
            {detail}
          </p>
        )}
      </div>
      {action}
    </div>
  );
}

/** Das Terminal. Rollt mit, solange man nicht selbst hochgescrollt hat. */
function Console({ lines, running }: { lines: LogLine[]; running: boolean }) {
  const boxRef = useRef<HTMLDivElement | null>(null);
  const stickRef = useRef(true);

  const onScroll = () => {
    const box = boxRef.current;
    if (!box) return;
    // 40px Toleranz: exakt am Ende landet man beim Scrollen nie.
    stickRef.current =
      box.scrollHeight - box.scrollTop - box.clientHeight < 40;
  };

  useEffect(() => {
    const box = boxRef.current;
    // Nur nachziehen, wenn der Leser unten steht. Sonst reißt es ihm
    // die Zeile weg, die er gerade liest.
    if (box && stickRef.current) box.scrollTop = box.scrollHeight;
  }, [lines.length]);

  return (
    <div className="rounded-2xl border border-slate-800 bg-[#080f1c] overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-slate-800/70 bg-[#0d1728]">
        <Terminal className="h-3.5 w-3.5 text-slate-500" />
        <span className="text-[11px] font-black uppercase tracking-widest text-slate-500">
          Live-Ausgabe
        </span>
        {running && (
          <Loader2 className="h-3 w-3 text-primary animate-spin ml-auto" />
        )}
      </div>
      <div
        ref={boxRef}
        onScroll={onScroll}
        className="h-[320px] overflow-y-auto px-4 py-3 font-mono text-[12px] leading-relaxed"
      >
        {lines.length === 0 ? (
          <p className="text-slate-600">Noch nichts passiert.</p>
        ) : (
          lines.map((line, index) => (
            <div key={index} className="flex gap-2.5">
              <span
                className={cn(
                  "shrink-0 font-bold",
                  line.source === "main" ? "text-sky-400" : "text-fuchsia-400"
                )}
              >
                {line.source === "main" ? "university" : "template "}
              </span>
              <span
                className={cn(
                  "break-words min-w-0",
                  line.level === "error" && "text-red-400",
                  line.level === "warn" && "text-amber-300",
                  line.level === "success" && "text-emerald-400",
                  !["error", "warn", "success"].includes(line.level) &&
                    "text-slate-400"
                )}
              >
                {line.text}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

/* ── Das Panel ──────────────────────────────────────────────────── */

export function SpeedrunPanel({ guildId }: { guildId: string }) {
  const { data: session } = useSession();
  const userId = session?.user?.id ?? "";

  const [stage, setStage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [pre, setPre] = useState<any>(null);
  const [templates, setTemplates] = useState<any[]>([]);
  const [chosen, setChosen] = useState<string>("");

  const [steps, setSteps] = useState<StepSpec[]>([]);
  const [options, setOptions] = useState<Record<string, boolean>>({});
  const [expanded, setExpanded] = useState(false);
  const [intros, setIntros] = useState(true);

  const [lines, setLines] = useState<LogLine[]>([]);
  const [phase, setPhase] = useState<"idle" | "building" | "finishing" | "done" | "failed">(
    "idle"
  );
  const [report, setReport] = useState<any>(null);
  const [progress, setProgress] = useState({ step: 0, total: 0 });

  // In Refs, nicht im State: der Poll-Timer liest sie, und ein State-Wert
  // wäre in seiner Closure eingefroren.
  const sinceRef = useRef(0);
  const sinceMainRef = useRef(0);
  const finishedRef = useRef(false);

  /* -- Laden ---------------------------------------------------- */

  const load = useCallback(async () => {
    try {
      const [precheck, list, stepList] = await Promise.all([
        api.speedrunPrecheck(guildId, userId),
        api.speedrunTemplates(userId),
        api.speedrunSteps(),
      ]);
      setPre(precheck);
      setTemplates(list?.templates ?? []);
      const specs: StepSpec[] = stepList?.steps ?? [];
      setSteps(specs);
      setOptions(
        Object.fromEntries(specs.map((s) => [s.key, s.default]))
      );

      // Ein einziges freigegebenes Template muss man nicht auswählen.
      const free = (list?.templates ?? []).filter((t: any) => t.available);
      if (free.length === 1) setChosen(free[0].key);
    } catch (err: any) {
      toast.error(err?.message || "Konnte nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [guildId, userId]);

  useEffect(() => {
    if (userId) load();
  }, [load, userId]);

  /* -- Fortschritt abfragen -------------------------------------- */

  const poll = useCallback(async () => {
    try {
      const data = await api.speedrunStatus(
        guildId,
        sinceRef.current,
        sinceMainRef.current
      );

      const fresh: LogLine[] = [
        ...(data?.lines ?? []),
        ...(data?.main?.lines ?? []),
      ];
      if (fresh.length) {
        // Nach Zeitstempel, sonst stehen die Zeilen des zweiten Bots
        // immer unten, auch wenn sie zeitlich dazwischen gehören.
        fresh.sort((a, b) => a.at - b.at);
        setLines((old) => [...old, ...fresh]);
      }
      sinceRef.current = data?.line_count ?? sinceRef.current;
      sinceMainRef.current = data?.main?.line_count ?? sinceMainRef.current;

      if (typeof data?.step === "number") {
        setProgress({ step: data.step, total: data.total ?? 0 });
      }

      const templateState = data?.state;
      const mainState = data?.main?.state;

      if (data?.main?.report) setReport(data.main.report);

      // Der Bau ist durch: die zweite Hälfte anstoßen. Genau einmal --
      // ohne diesen Riegel startet jede Abfrage einen neuen Durchlauf.
      if (
        templateState === "done" &&
        mainState === "none" &&
        !finishedRef.current
      ) {
        finishedRef.current = true;
        setPhase("finishing");
        try {
          await api.speedrunFinish(guildId, options);
        } catch (err: any) {
          setPhase("failed");
          toast.error(err?.message || "Die Einrichtung ließ sich nicht starten.");
        }
        return;
      }

      if (templateState === "failed") {
        setPhase("failed");
        return;
      }
      if (["done", "partial", "failed"].includes(mainState)) {
        setPhase(mainState === "failed" ? "failed" : "done");
      }
    } catch (err: any) {
      // Ein einzelner Fehlschlag ist normal (Neustart, kurzer Aussetzer).
      // Erst nach dem Ende hört das Abfragen auf.
      console.error("[speedrun] poll", err);
    }
  }, [guildId, options]);

  useEffect(() => {
    if (phase !== "building" && phase !== "finishing") return;
    const timer = setInterval(poll, POLL_MS);
    poll();
    return () => clearInterval(timer);
  }, [phase, poll]);

  /* -- Starten --------------------------------------------------- */

  const start = async () => {
    setBusy(true);
    try {
      await api.speedrunStart(guildId, {
        template: chosen,
        user_id: userId,
        options: { intros, rebuild: false },
      });
      sinceRef.current = 0;
      sinceMainRef.current = 0;
      finishedRef.current = false;
      setLines([]);
      setReport(null);
      setPhase("building");
      setStage(3);
    } catch (err: any) {
      toast.error(err?.message || "Der Start ist fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  /* -- Ansicht --------------------------------------------------- */

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="h-8 w-8 text-primary animate-spin opacity-40" />
      </div>
    );
  }

  const checks = pre?.checks ?? {};
  const ready = Boolean(pre?.ready);
  const running = phase === "building" || phase === "finishing";
  const chosenTemplate = templates.find((t) => t.key === chosen);

  return (
    <section className="space-y-6">
      {/* ── Kopf ─────────────────────────────────────────── */}
      <div className={cn(CARD, "space-y-4")}>
        <div className="flex gap-3">
          <div className="h-10 w-10 rounded-2xl bg-primary/15 grid place-items-center shrink-0">
            <Gauge className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0">
            <p className="font-black text-white flex items-center gap-2 flex-wrap">
              Speedrun
              <span className="px-1.5 py-0.5 rounded text-[9px] font-black tracking-widest bg-amber-400/15 text-amber-300/90">
                BETA
              </span>
            </p>
            <p className="text-[12px] text-slate-400 mt-1 leading-relaxed">
              Der Template-Bot baut Rollen und Kanäle, danach richtet der
              University Bot Verify, Logs, Anti-Nuke und Tickets ein. Du
              siehst unten mit, was gerade passiert.
            </p>
          </div>
        </div>

        <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/20 p-3.5 flex gap-2.5">
          <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
          <p className="text-[12px] text-amber-200/80 leading-relaxed">
            Ein Speedrun legt Dutzende Rollen und Kanäle an und lässt sich
            nicht per Knopfdruck rückgängig machen. Vorhandene Kanäle
            bleiben stehen — gelöscht wird nichts.
          </p>
        </div>

        <StepDots current={stage} />
      </div>

      {/* ── 1. Voraussetzungen ───────────────────────────── */}
      {stage === 0 && (
        <div className={cn(CARD, "space-y-1")}>
          <p className="text-xs font-black uppercase tracking-widest text-slate-500 mb-3">
            Voraussetzungen
          </p>

          <Requirement
            ok={Boolean(checks.main_bot_present)}
            label="University Bot ist auf dem Server"
            detail={
              checks.main_bot_present
                ? undefined
                : "Ohne ihn kann hier nichts eingerichtet werden."
            }
          />
          <Requirement
            ok={Boolean(checks.main_bot_can_manage)}
            label="University Bot darf Rollen und Kanäle verwalten"
            detail={
              checks.main_bot_can_manage
                ? undefined
                : "Gib der Bot-Rolle „Rollen verwalten“ und „Kanäle verwalten“."
            }
          />
          <Requirement
            ok={Boolean(checks.template_bot_present)}
            label="Template-Bot ist auf dem Server"
            detail={
              checks.template_bot_present
                ? undefined
                : pre?.detail ||
                  "Lade den zweiten Bot ein — er baut die Struktur."
            }
            action={
              !checks.template_bot_present && pre?.template_invite ? (
                <a
                  href={pre.template_invite}
                  target="_blank"
                  rel="noreferrer"
                  className="shrink-0 px-3 py-1.5 rounded-lg bg-primary text-white text-[11px] font-black uppercase tracking-wider hover:bg-primary/80 transition-colors"
                >
                  Einladen
                </a>
              ) : undefined
            }
          />

          {!checks.template_bot_reachable && (
            <div className="rounded-xl bg-red-500/[0.06] border border-red-500/20 p-3.5 flex gap-2.5 mt-3">
              <XCircle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
              <p className="text-[12px] text-red-200/80 leading-relaxed">
                Der Template-Bot antwortet gerade nicht.
                {pre?.detail ? ` ${pre.detail}` : ""}
              </p>
            </div>
          )}

          <div className="flex items-center gap-2 pt-4">
            <button
              onClick={() => {
                setLoading(true);
                load();
              }}
              className="px-3.5 py-2 rounded-xl border border-slate-800 text-slate-400 text-[11px] font-black uppercase tracking-wider hover:text-white hover:border-slate-700 transition-colors inline-flex items-center gap-2"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Neu prüfen
            </button>
            <button
              disabled={!ready}
              onClick={() => setStage(1)}
              className={cn(
                "ml-auto px-4 py-2 rounded-xl text-[11px] font-black uppercase tracking-wider transition-colors inline-flex items-center gap-2",
                ready
                  ? "bg-primary text-white hover:bg-primary/80"
                  : "bg-slate-800 text-slate-600 cursor-not-allowed"
              )}
            >
              Weiter
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* ── 2. Vorlage ───────────────────────────────────── */}
      {stage === 1 && (
        <div className={cn(CARD, "space-y-4")}>
          <div>
            <p className="text-xs font-black uppercase tracking-widest text-slate-500">
              Vorlage
            </p>
            <p className="text-[12px] text-slate-500 mt-1">
              In der Beta ist erst eine Vorlage freigegeben — auch mit
              Premium. Die übrigen sind gebaut, aber noch nicht auf einem
              echten Server gelaufen.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {templates.map((template) => {
              const locked = !template.available;
              const active = chosen === template.key;
              return (
                <button
                  key={template.key}
                  disabled={locked}
                  onClick={() => setChosen(template.key)}
                  className={cn(
                    "text-left rounded-2xl border p-4 transition-colors",
                    locked && "opacity-45 cursor-not-allowed border-slate-800/60 bg-[#0d1b31]",
                    !locked && active && "border-primary/60 bg-primary/[0.08]",
                    !locked && !active &&
                      "border-slate-800 bg-[#0d1b31] hover:border-slate-700"
                  )}
                >
                  <div className="flex items-start gap-2.5">
                    <span className="text-lg shrink-0">{template.emoji}</span>
                    <div className="min-w-0 flex-1">
                      <p className="font-black text-white text-sm flex items-center gap-2">
                        {template.name}
                        {locked && (
                          <Lock className="h-3 w-3 text-slate-500 shrink-0" />
                        )}
                        {active && !locked && (
                          <CheckCircle2 className="h-3.5 w-3.5 text-primary shrink-0" />
                        )}
                      </p>
                      <p className="text-[11px] text-slate-500 mt-1 leading-relaxed">
                        {template.tagline}
                      </p>
                      <p className="text-[10px] text-slate-600 mt-2 font-bold uppercase tracking-wider">
                        {template.role_count} Rollen ·{" "}
                        {template.category_count} Kategorien
                      </p>
                      {locked && template.locked_reason && (
                        <p className="text-[10px] text-amber-300/70 mt-2 leading-relaxed">
                          {template.locked_reason}
                        </p>
                      )}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-2 pt-1">
            <button
              onClick={() => setStage(0)}
              className="px-3.5 py-2 rounded-xl border border-slate-800 text-slate-400 text-[11px] font-black uppercase tracking-wider hover:text-white transition-colors inline-flex items-center gap-2"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Zurück
            </button>
            <button
              disabled={!chosen}
              onClick={() => setStage(2)}
              className={cn(
                "ml-auto px-4 py-2 rounded-xl text-[11px] font-black uppercase tracking-wider transition-colors inline-flex items-center gap-2",
                chosen
                  ? "bg-primary text-white hover:bg-primary/80"
                  : "bg-slate-800 text-slate-600 cursor-not-allowed"
              )}
            >
              Weiter
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* ── 3. Umfang ────────────────────────────────────── */}
      {stage === 2 && (
        <div className={cn(CARD, "space-y-4")}>
          <div>
            <p className="text-xs font-black uppercase tracking-widest text-slate-500">
              Umfang
            </p>
            <p className="text-[12px] text-slate-500 mt-1">
              Standard richtet alles Übliche ein. Aufklappen, wenn du
              einzelne Sachen weglassen willst.
            </p>
          </div>

          <div className="rounded-2xl border border-primary/30 bg-primary/[0.06] p-4 flex gap-3">
            <Sparkles className="h-4 w-4 text-primary shrink-0 mt-0.5" />
            <div className="min-w-0">
              <p className="text-sm font-black text-white">
                Standard: {Object.values(options).filter(Boolean).length} von{" "}
                {steps.length} Schritten
              </p>
              <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                {steps
                  .filter((step) => options[step.key])
                  .map((step) => step.label)
                  .join(" · ") || "Nichts ausgewählt."}
              </p>
            </div>
          </div>

          <button
            onClick={() => setExpanded((open) => !open)}
            className="w-full flex items-center gap-2.5 px-4 py-3 rounded-2xl border border-slate-800 bg-[#0d1b31] hover:border-slate-700 transition-colors"
          >
            <span className="text-[11px] font-black uppercase tracking-wider text-slate-400">
              Erweitert — einzeln einstellen
            </span>
            <ChevronDown
              className={cn(
                "h-3.5 w-3.5 text-slate-600 ml-auto transition-transform",
                expanded && "rotate-180"
              )}
            />
          </button>

          {expanded && (
            <div className="space-y-3.5 rounded-2xl border border-slate-800 bg-[#0d1b31] p-4">
              <p className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                Template-Bot
              </p>
              <InlineToggle
                checked={intros}
                onCheckedChange={setIntros}
                label="Startnachrichten in die Kanäle"
                hint="Eine angeheftete Erklärung pro Kanal. Aus, wenn die Kanäle leer bleiben sollen."
              />

              <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 pt-2">
                University Bot
              </p>
              {steps.map((step) => (
                <InlineToggle
                  key={step.key}
                  checked={Boolean(options[step.key])}
                  onCheckedChange={(value) =>
                    setOptions((old) => ({ ...old, [step.key]: value }))
                  }
                  label={step.label}
                  hint={step.description}
                />
              ))}
            </div>
          )}

          <div className="flex items-center gap-2 pt-1">
            <button
              onClick={() => setStage(1)}
              className="px-3.5 py-2 rounded-xl border border-slate-800 text-slate-400 text-[11px] font-black uppercase tracking-wider hover:text-white transition-colors inline-flex items-center gap-2"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Zurück
            </button>
            <button
              disabled={busy}
              onClick={start}
              className="ml-auto px-4 py-2 rounded-xl bg-primary text-white text-[11px] font-black uppercase tracking-wider hover:bg-primary/80 transition-colors inline-flex items-center gap-2 disabled:opacity-50"
            >
              {busy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Rocket className="h-3.5 w-3.5" />
              )}
              {chosenTemplate ? `„${chosenTemplate.name}“ bauen` : "Starten"}
            </button>
          </div>
        </div>
      )}

      {/* ── 4. Lauf ──────────────────────────────────────── */}
      {stage === 3 && (
        <div className={cn(CARD, "space-y-4")}>
          <div className="flex items-center gap-3 flex-wrap">
            <p className="text-xs font-black uppercase tracking-widest text-slate-500">
              {phase === "building" && "Der Template-Bot baut…"}
              {phase === "finishing" && "Der University Bot richtet ein…"}
              {phase === "done" && "Fertig"}
              {phase === "failed" && "Abgebrochen"}
              {phase === "idle" && "Bereit"}
            </p>
            {progress.total > 0 && running && (
              <span className="text-[11px] font-mono text-slate-500">
                {progress.step}/{progress.total}
              </span>
            )}
            {phase === "done" && (
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            )}
            {phase === "failed" && <XCircle className="h-4 w-4 text-red-400" />}
          </div>

          {progress.total > 0 && (
            <div className="h-1.5 rounded-full bg-slate-800 overflow-hidden">
              <div
                className="h-full bg-primary transition-all duration-500"
                style={{
                  width: `${Math.min(
                    100,
                    Math.round((progress.step / progress.total) * 100)
                  )}%`,
                }}
              />
            </div>
          )}

          <Console lines={lines} running={running} />

          {report && (
            <div className="space-y-1.5">
              <p className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                Was der University Bot eingerichtet hat
              </p>
              {report.steps?.map((step: any) => (
                <div key={step.key} className="flex items-start gap-2.5 py-1">
                  {step.ok ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-0.5" />
                  ) : (
                    <Circle className="h-3.5 w-3.5 text-amber-400 shrink-0 mt-0.5" />
                  )}
                  <p
                    className={cn(
                      "text-[12px] leading-relaxed",
                      step.ok ? "text-slate-400" : "text-amber-200/80"
                    )}
                  >
                    {step.detail || step.key}
                  </p>
                </div>
              ))}
            </div>
          )}

          {!running && (
            <button
              onClick={() => {
                setStage(0);
                setPhase("idle");
                setLines([]);
                setReport(null);
                setLoading(true);
                load();
              }}
              className="px-3.5 py-2 rounded-xl border border-slate-800 text-slate-400 text-[11px] font-black uppercase tracking-wider hover:text-white transition-colors inline-flex items-center gap-2"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Von vorne
            </button>
          )}
        </div>
      )}
    </section>
  );
}
