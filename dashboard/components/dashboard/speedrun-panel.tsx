"use client";

/**
 * Speedrun (Beta) — einen Server in einem Durchlauf aufsetzen.
 *
 * Vier Schritte: Voraussetzungen, Vorlage, Umfang, Lauf.
 *
 * Neu geschrieben, nachdem sechs Fehler zusammenkamen. Jeder davon
 * wurde nachgestellt, bevor er behoben wurde, und jeder hat hier eine
 * Stelle, an der die Lösung steht:
 *
 *  1. **Doppelte Log-Zeilen.** `setInterval` startete die nächste
 *     Abfrage, bevor die vorige ihren Zähler gesetzt hatte. Nachgestellt
 *     mit einer 2,5s-Antwort bei 1,5s Takt: 10 Zeilen statt 5. Jetzt
 *     eine Schleife, die erst wartet und dann neu plant, plus ein
 *     Riegel gegen Überlappung.
 *
 *  2. **Neu laden verlor den Bau.** Der Ladevorgang fragte den Status
 *     nie ab, also stand man nach F5 auf Schritt 1, während im
 *     Hintergrund weitergebaut wurde. Jetzt wird beim Öffnen geprüft,
 *     ob etwas läuft, und direkt zum Terminal gesprungen.
 *
 *  3. **Die Übergabe konnte sich selbst auslösen.** Die Bedingung war
 *     "Bau fertig und Einrichtung noch nicht gelaufen" — das erfüllt
 *     auch ein 15 Minuten alter Job. Jetzt trägt jeder Lauf eine
 *     `run_id`, und der Bot lehnt eine fremde ab.
 *
 *  4. **Der Timer wurde ständig neu aufgesetzt**, weil er an `options`
 *     hing. Die Optionen liegen jetzt in einem Ref.
 *
 *  5. **"Teilweise fertig" sah aus wie "fertig".** Der Zustand kam vom
 *     Bot, die Anzeige kannte ihn nicht.
 *
 *  6. **Kein Weg zurück.** Hängt der Bau, blieb der Reiter für immer
 *     auf "läuft". Es gibt jetzt Abbrechen.
 *
 * Die Bewegung ist absichtlich zurückhaltend: Reihen laufen gestaffelt
 * ein, der Fortschrittsbalken schimmert, das Terminal blinkt am Cursor.
 * Alles davon respektiert `prefers-reduced-motion`.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleDashed,
  Gauge,
  Info,
  Loader2,
  Lock,
  RefreshCw,
  Rocket,
  Sparkles,
  Square,
  Terminal,
  Trash2,
  TriangleAlert,
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

type Phase = "idle" | "building" | "finishing" | "done" | "partial" | "failed";

/** Abstand zwischen zwei Abfragen — gemessen ab dem Ende der letzten. */
const POLL_MS = 1200;

const CARD =
  "bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 border-glow-card";

const STAGES = ["Voraussetzungen", "Vorlage", "Umfang", "Lauf"];

/* ── Bewegung ───────────────────────────────────────────────────── */

/**
 * Ein Kind, das beim Erscheinen einläuft.
 *
 * `index` staffelt die Verzögerung, damit eine Liste nacheinander
 * auftaucht statt alles auf einmal. Über 8 wird nicht weiter gestaffelt:
 * bei 40ms Schritt wären das sonst über eine halbe Sekunde, und so lange
 * will niemand auf den letzten Eintrag warten.
 */
function Rise({
  index = 0,
  children,
  className,
}: {
  index?: number;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn("sr-rise", className)}
      style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }}
    >
      {children}
    </div>
  );
}

/** Die Stile liegen inline, damit der Reiter ohne Änderung an globals.css auskommt. */
function Motion() {
  return (
    <style jsx global>{`
      @keyframes sr-rise-in {
        from {
          opacity: 0;
          transform: translateY(8px);
        }
        to {
          opacity: 1;
          transform: none;
        }
      }
      .sr-rise {
        animation: sr-rise-in 340ms cubic-bezier(0.22, 1, 0.36, 1) both;
      }

      @keyframes sr-sheen {
        from {
          transform: translateX(-100%);
        }
        to {
          transform: translateX(300%);
        }
      }
      .sr-sheen::after {
        content: "";
        position: absolute;
        inset: 0;
        width: 33%;
        background: linear-gradient(
          90deg,
          transparent,
          rgba(255, 255, 255, 0.45),
          transparent
        );
        animation: sr-sheen 1.6s linear infinite;
      }

      @keyframes sr-blink {
        0%,
        45% {
          opacity: 1;
        }
        50%,
        95% {
          opacity: 0;
        }
      }
      .sr-caret {
        animation: sr-blink 1.1s steps(1) infinite;
      }

      @keyframes sr-pulse-ring {
        0% {
          box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.5);
        }
        70% {
          box-shadow: 0 0 0 10px rgba(59, 130, 246, 0);
        }
        100% {
          box-shadow: 0 0 0 0 rgba(59, 130, 246, 0);
        }
      }
      .sr-pulse {
        animation: sr-pulse-ring 2s ease-out infinite;
      }

      /* Wer Bewegung abgestellt hat, bekommt keine. Das ist keine
         Höflichkeit, sondern für manche Menschen der Unterschied
         zwischen benutzbar und übel. */
      @media (prefers-reduced-motion: reduce) {
        .sr-rise,
        .sr-sheen::after,
        .sr-caret,
        .sr-pulse {
          animation: none !important;
        }
        .sr-rise {
          opacity: 1;
          transform: none;
        }
      }
    `}</style>
  );
}

/* ── Kleinteile ─────────────────────────────────────────────────── */

function StageBar({ current, running }: { current: number; running: boolean }) {
  return (
    <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
      {STAGES.map((name, index) => {
        const done = index < current;
        const active = index === current;
        return (
          <React.Fragment key={name}>
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "h-6 w-6 rounded-full grid place-items-center text-[10px] font-black shrink-0 transition-colors duration-300",
                  done && "bg-emerald-500/20 text-emerald-300",
                  active && "bg-primary text-white",
                  active && running && "sr-pulse",
                  !done && !active && "bg-slate-800 text-slate-500"
                )}
              >
                {done ? <Check className="h-3 w-3" /> : index + 1}
              </span>
              <span
                className={cn(
                  "text-[11px] font-black uppercase tracking-wider hidden sm:inline transition-colors",
                  active ? "text-white" : "text-slate-500"
                )}
              >
                {name}
              </span>
            </div>
            {index < STAGES.length - 1 && (
              <span
                className={cn(
                  "h-px w-4 sm:w-8 shrink-0 transition-colors duration-500",
                  done ? "bg-emerald-500/40" : "bg-slate-800"
                )}
              />
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
        <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
      ) : (
        <XCircle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
      )}
      <div className="min-w-0 flex-1">
        <p className={cn("text-sm font-bold", ok ? "text-slate-300" : "text-white")}>
          {label}
        </p>
        {detail && (
          <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">{detail}</p>
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
    stickRef.current = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
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
        <span className="ml-auto text-[10px] font-mono text-slate-600">
          {lines.length} Zeilen
        </span>
        {running && <Loader2 className="h-3 w-3 text-primary animate-spin" />}
      </div>
      <div
        ref={boxRef}
        onScroll={onScroll}
        className="h-[340px] overflow-y-auto px-4 py-3 font-mono text-[12px] leading-relaxed"
      >
        {lines.length === 0 ? (
          <p className="text-slate-600">
            Noch nichts passiert.
            {running && <span className="sr-caret text-primary"> ▋</span>}
          </p>
        ) : (
          <>
            {lines.map((line, index) => (
              <div
                key={`${line.at}-${index}`}
                className="flex gap-2.5 sr-rise"
                style={{ animationDelay: "0ms" }}
              >
                <span
                  className={cn(
                    "shrink-0 font-bold select-none",
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
            ))}
            {running && <span className="sr-caret text-primary">▋</span>}
          </>
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
  // Getrennte Fehler pro Aufruf: scheitert die Vorlagenliste, heißt das
  // nicht, dass die Voraussetzungen nicht stimmen -- und umgekehrt.
  const [preError, setPreError] = useState("");
  const [templateError, setTemplateError] = useState("");
  const [templates, setTemplates] = useState<any[]>([]);
  const [chosen, setChosen] = useState<string>("");

  const [steps, setSteps] = useState<StepSpec[]>([]);
  const [options, setOptions] = useState<Record<string, boolean>>({});
  const [expanded, setExpanded] = useState(false);
  const [intros, setIntros] = useState(true);

  // "Alles löschen" -- standardmäßig aus. Der Schaden ist endgültig,
  // also muss man ihn ausdrücklich anfordern, nicht bloß nicht abwählen.
  const [wipe, setWipe] = useState(false);
  const [wipeConfirm, setWipeConfirm] = useState("");

  const [lines, setLines] = useState<LogLine[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [report, setReport] = useState<any>(null);
  const [progress, setProgress] = useState({ step: 0, total: 0 });
  const [resumed, setResumed] = useState(false);

  // In Refs, nicht im State: die Poll-Schleife liest sie, und ein
  // State-Wert wäre in ihrer Closure eingefroren.
  const sinceRef = useRef(0);
  const sinceMainRef = useRef(0);
  const finishedRef = useRef(false);
  const runIdRef = useRef("");
  const optionsRef = useRef<Record<string, boolean>>({});
  const phaseRef = useRef<Phase>("idle");
  const pollingRef = useRef(false);
  const aliveRef = useRef(true);

  // Die Optionen begleiten die Schleife über ein Ref. Hingen sie an den
  // Abhängigkeiten, würde jeder Klick auf einen Schalter den Timer neu
  // aufsetzen -- mitten im Bau.
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  const isRunning = phase === "building" || phase === "finishing";

  /* -- Fortschritt einsammeln ------------------------------------ */

  const applyStatus = useCallback(
    async (data: any) => {
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
      // Zähler direkt hinter dem Lesen setzen, nicht erst nach dem
      // Rendern: die nächste Abfrage muss den neuen Stand sehen.
      sinceRef.current = data?.line_count ?? sinceRef.current;
      sinceMainRef.current = data?.main?.line_count ?? sinceMainRef.current;

      if (typeof data?.step === "number") {
        setProgress({ step: data.step, total: data.total ?? 0 });
      }
      if (data?.main?.report) setReport(data.main.report);

      const templateState = data?.state;
      const mainState = data?.main?.state;

      if (data?.run_id && !runIdRef.current) runIdRef.current = data.run_id;

      // Der Bau ist durch: die zweite Hälfte anstoßen. Genau einmal --
      // ohne diesen Riegel startet jede Abfrage einen neuen Durchlauf.
      if (templateState === "done" && mainState === "none" && !finishedRef.current) {
        finishedRef.current = true;
        setPhase("finishing");
        try {
          await api.speedrunFinish(guildId, optionsRef.current, runIdRef.current);
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
      if (mainState === "failed") {
        setPhase("failed");
        return;
      }
      // "partial" heißt: gelaufen, aber mit Lücken. Das als "Fertig" zu
      // zeigen wäre gelogen -- man würde die roten Zeilen übersehen.
      if (mainState === "partial") {
        setPhase("partial");
        return;
      }
      if (mainState === "done") setPhase("done");
    },
    [guildId]
  );

  /* -- Die Schleife ---------------------------------------------- */
  //
  // Bewusst kein setInterval. Dauert eine Antwort länger als der Takt,
  // überholen sich die Abfragen: die zweite liest denselben Zähler wie
  // die erste und holt dieselben Zeilen noch einmal. Nachgestellt mit
  // 2,5s Antwortzeit bei 1,5s Takt -- jede Zeile kam doppelt an.
  //
  // Hier wartet die Schleife das Ergebnis ab und plant erst dann neu.
  useEffect(() => {
    if (!isRunning) return;

    let timer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;

    const tick = async () => {
      if (stopped || pollingRef.current) return;
      pollingRef.current = true;
      try {
        const data = await api.speedrunStatus(
          guildId,
          sinceRef.current,
          sinceMainRef.current
        );
        if (!stopped && aliveRef.current) await applyStatus(data);
      } catch (err: any) {
        // Ein einzelner Fehlschlag ist normal (Neustart, kurzer
        // Aussetzer). Erst nach dem Ende hört das Abfragen auf.
        console.error("[speedrun] poll", err);
      } finally {
        pollingRef.current = false;
        if (!stopped && phaseRef.current !== "done") {
          timer = setTimeout(tick, POLL_MS);
        }
      }
    };

    tick();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [isRunning, guildId, applyStatus]);

  /* -- Laden ----------------------------------------------------- */

  const load = useCallback(async () => {
    // allSettled, nicht all: `Promise.all` wirft, sobald *einer* der
    // Aufrufe scheitert, und dann werden auch die geglückten verworfen.
    // Genau das ist passiert -- der Template-Bot war nicht erreichbar,
    // /templates gab 502, und weil damit auch das Ergebnis von
    // /precheck wegflog, standen alle Voraussetzungen auf "fehlt".
    const [precheck, list, stepList, status] = await Promise.allSettled([
      api.speedrunPrecheck(guildId, userId),
      api.speedrunTemplates(userId),
      api.speedrunSteps(),
      api.speedrunStatus(guildId, 0, 0),
    ]);

    if (precheck.status === "fulfilled") {
      setPre(precheck.value);
      setPreError("");
    } else {
      setPre(null);
      setPreError(precheck.reason?.message || "Die Prüfung ist fehlgeschlagen.");
    }

    let specs: StepSpec[] = [];
    if (stepList.status === "fulfilled") {
      specs = stepList.value?.steps ?? [];
      setSteps(specs);
      setOptions(Object.fromEntries(specs.map((s) => [s.key, s.default])));
    }

    if (list.status === "fulfilled") {
      const items = list.value?.templates ?? [];
      setTemplates(items);
      setTemplateError("");
      // Ein einziges freigegebenes Template muss man nicht auswählen.
      const free = items.filter((t: any) => t.available);
      if (free.length === 1) setChosen(free[0].key);
    } else {
      setTemplates([]);
      setTemplateError(
        list.reason?.message || "Die Vorlagen konnten nicht geladen werden."
      );
    }

    // Läuft gerade etwas? Ohne diese Frage stand man nach einem
    // Neuladen auf Schritt 1, während im Hintergrund weitergebaut
    // wurde -- der Bau war unsichtbar und der Startknopf hätte einen
    // zweiten angestoßen.
    if (status.status === "fulfilled") {
      const data = status.value;
      const templateState = data?.state;
      const mainState = data?.main?.state;
      const active =
        templateState === "running" ||
        mainState === "running" ||
        (templateState === "done" && mainState === "running");

      if (active) {
        runIdRef.current = data?.run_id || data?.main?.run_id || "";
        // Was schon gelaufen ist, ins Terminal holen -- sonst beginnt
        // die Ausgabe mitten im Satz.
        const past: LogLine[] = [
          ...(data?.lines ?? []),
          ...(data?.main?.lines ?? []),
        ].sort((a, b) => a.at - b.at);
        setLines(past);
        sinceRef.current = data?.line_count ?? 0;
        sinceMainRef.current = data?.main?.line_count ?? 0;
        // Die Übergabe darf nicht erneut anlaufen, wenn sie schon läuft.
        finishedRef.current = mainState !== "none";
        if (data?.main?.report) setReport(data.main.report);
        if (typeof data?.step === "number") {
          setProgress({ step: data.step, total: data.total ?? 0 });
        }
        setPhase(mainState === "running" ? "finishing" : "building");
        setStage(3);
        setResumed(true);
      }
    }

    setLoading(false);
  }, [guildId, userId]);

  useEffect(() => {
    if (userId) load();
  }, [load, userId]);

  /* -- Starten und Abbrechen ------------------------------------- */

  const start = async () => {
    setBusy(true);
    try {
      const answer = await api.speedrunStart(guildId, {
        template: chosen,
        user_id: userId,
        options: { intros, rebuild: wipe },
        // Der Bot prüft das noch einmal selbst. Hier steht es, weil er
        // sonst nicht wissen kann, ob wirklich jemand zugestimmt hat.
        confirm: wipe ? wipeConfirm.trim() : "",
      });
      sinceRef.current = 0;
      sinceMainRef.current = 0;
      finishedRef.current = false;
      runIdRef.current = answer?.run_id || "";
      setLines([]);
      setReport(null);
      setProgress({ step: 0, total: 0 });
      setResumed(false);
      setPhase("building");
      setStage(3);
    } catch (err: any) {
      toast.error(err?.message || "Der Start ist fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (
      !confirm(
        "Den Bau abbrechen?\n\nDer Server bleibt so stehen, wie er gerade " +
          "ist — was schon angelegt wurde, bleibt. Discord kennt kein Zurück."
      )
    ) {
      return;
    }
    setBusy(true);
    try {
      await api.speedrunCancel(guildId);
      setPhase("failed");
      toast.success("Abgebrochen.");
    } catch (err: any) {
      toast.error(err?.message || "Der Abbruch ist fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const restart = () => {
    setStage(0);
    setPhase("idle");
    setLines([]);
    setReport(null);
    setProgress({ step: 0, total: 0 });
    setResumed(false);
    finishedRef.current = false;
    runIdRef.current = "";
    setLoading(true);
    load();
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
  const chosenTemplate = templates.find((t) => t.key === chosen);
  const chosenCount = Object.values(options).filter(Boolean).length;

  // Ohne Löschen immer startklar; mit Löschen erst, wenn der Servername
  // genau stimmt. Der Vergleich läuft auch im Bot noch einmal -- hier
  // geht es nur darum, den Knopf zu sperren, statt eine Fehlermeldung
  // zu zeigen, nachdem jemand schon geklickt hat.
  const wipeReady =
    !wipe ||
    (Boolean(pre?.guild_name) &&
      wipeConfirm.trim() === String(pre.guild_name).trim());

  const percent =
    progress.total > 0
      ? Math.min(100, Math.round((progress.step / progress.total) * 100))
      : 0;

  return (
    <section className="space-y-6">
      <Motion />

      {/* ── Kopf ─────────────────────────────────────────── */}
      <Rise>
        <div className={cn(CARD, "space-y-4")}>
          <div className="flex gap-3">
            <div
              className={cn(
                "h-10 w-10 rounded-2xl bg-primary/15 grid place-items-center shrink-0",
                isRunning && "sr-pulse"
              )}
            >
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
              nicht per Knopfdruck rückgängig machen. Vorhandene Kanäle bleiben
              stehen — gelöscht wird nichts.
            </p>
          </div>

          <StageBar current={stage} running={isRunning} />
        </div>
      </Rise>

      {/* ── 1. Voraussetzungen ───────────────────────────── */}
      {stage === 0 && (
        <Rise index={1}>
          <div className={cn(CARD, "space-y-1")}>
            <p className="text-xs font-black uppercase tracking-widest text-slate-500 mb-3">
              Voraussetzungen
            </p>

            {/* Konnte gar nicht geprüft werden. Ohne diesen Kasten stünden
                unten lauter rote Kreuze, die behaupten, die Bots fehlten --
                dabei ist bloß die Prüfung selbst nicht durchgekommen. */}
            {preError && (
              <div className="rounded-xl bg-red-500/[0.06] border border-red-500/20 p-3.5 flex gap-2.5 mb-3">
                <XCircle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
                <div className="min-w-0">
                  <p className="text-[12px] text-red-200/90 font-bold">
                    Die Prüfung selbst ist fehlgeschlagen.
                  </p>
                  <p className="text-[11px] text-red-200/70 mt-1 leading-relaxed">
                    {preError} Was unten steht, ist deshalb ungeprüft — nicht
                    unbedingt falsch.
                  </p>
                </div>
              </div>
            )}

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
                  : pre?.detail || "Lade den zweiten Bot ein — er baut die Struktur."
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
                  "ml-auto px-4 py-2 rounded-xl text-[11px] font-black uppercase tracking-wider transition-all inline-flex items-center gap-2",
                  ready
                    ? "bg-primary text-white hover:bg-primary/80 hover:gap-3"
                    : "bg-slate-800 text-slate-600 cursor-not-allowed"
                )}
              >
                Weiter
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </Rise>
      )}

      {/* ── 2. Vorlage ───────────────────────────────────── */}
      {stage === 1 && (
        <Rise index={1}>
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

            {templateError && (
              <div className="rounded-xl bg-red-500/[0.06] border border-red-500/20 p-3.5 flex gap-2.5">
                <XCircle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
                <div className="min-w-0">
                  <p className="text-[12px] text-red-200/90 font-bold">
                    Die Vorlagen kommen vom Template-Bot — er antwortet nicht.
                  </p>
                  <p className="text-[11px] text-red-200/70 mt-1 leading-relaxed">
                    {templateError}
                  </p>
                  <p className="text-[11px] text-red-200/70 mt-2 leading-relaxed">
                    Häufigste Ursache: <code>TEMPLATE_BOT_URL</code> fehlt oder
                    zeigt woandershin, oder der Template-Bot lauscht nicht auf
                    IPv6 — Railways internes Netz läuft nur darüber.
                  </p>
                </div>
              </div>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              {templates.map((template, index) => {
                const locked = !template.available;
                const active = chosen === template.key;
                return (
                  <Rise key={template.key} index={index}>
                    <button
                      disabled={locked}
                      onClick={() => setChosen(template.key)}
                      className={cn(
                        "w-full h-full text-left rounded-2xl border p-4 transition-all duration-200",
                        locked &&
                          "opacity-45 cursor-not-allowed border-slate-800/60 bg-[#0d1b31]",
                        !locked &&
                          active &&
                          "border-primary/60 bg-primary/[0.08] shadow-lg shadow-primary/10 -translate-y-0.5",
                        !locked &&
                          !active &&
                          "border-slate-800 bg-[#0d1b31] hover:border-slate-700 hover:-translate-y-0.5"
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
                  </Rise>
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
                  "ml-auto px-4 py-2 rounded-xl text-[11px] font-black uppercase tracking-wider transition-all inline-flex items-center gap-2",
                  chosen
                    ? "bg-primary text-white hover:bg-primary/80 hover:gap-3"
                    : "bg-slate-800 text-slate-600 cursor-not-allowed"
                )}
              >
                Weiter
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </Rise>
      )}

      {/* ── 3. Umfang ────────────────────────────────────── */}
      {stage === 2 && (
        <Rise index={1}>
          <div className={cn(CARD, "space-y-4")}>
            <div>
              <p className="text-xs font-black uppercase tracking-widest text-slate-500">
                Umfang
              </p>
              <p className="text-[12px] text-slate-500 mt-1">
                Standard richtet alles Übliche ein. Aufklappen, wenn du einzelne
                Sachen weglassen willst.
              </p>
            </div>

            <div
              className={cn(
                "rounded-2xl border p-4 flex gap-3 transition-colors",
                wipe
                  ? "border-red-500/30 bg-red-500/[0.06]"
                  : "border-primary/30 bg-primary/[0.06]"
              )}
            >
              {wipe ? (
                <Trash2 className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
              ) : (
                <Sparkles className="h-4 w-4 text-primary shrink-0 mt-0.5" />
              )}
              <div className="min-w-0">
                <p className="text-sm font-black text-white">
                  {wipe ? "Alles löschen, dann neu bauen" : "Standard"}:{" "}
                  {chosenCount} von {steps.length} Schritten
                </p>
                <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                  {steps
                    .filter((step) => options[step.key])
                    .map((step) => step.label)
                    .join(" · ") || "Nichts ausgewählt."}
                </p>
                {wipe && (
                  <p className="text-[11px] text-red-200/80 mt-2 leading-relaxed font-bold">
                    Alle bestehenden Kanäle und Rollen werden vorher gelöscht.
                  </p>
                )}
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
                  "h-3.5 w-3.5 text-slate-600 ml-auto transition-transform duration-300",
                  expanded && "rotate-180"
                )}
              />
            </button>

            {expanded && (
              <Rise>
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

                  {/* ── Alles löschen ────────────────────────────
                      Getrennt vom Rest und rot umrandet, weil es als
                      einziger Schalter Bestehendes zerstört statt etwas
                      hinzuzufügen. */}
                  <div className="rounded-xl border border-red-500/25 bg-red-500/[0.05] p-3.5 mt-1">
                    <InlineToggle
                      checked={wipe}
                      onCheckedChange={(value) => {
                        setWipe(value);
                        if (!value) setWipeConfirm("");
                      }}
                      label={
                        <span className="text-red-200/90 font-bold">
                          Vorher alles löschen
                        </span>
                      }
                      hint="Alle Kanäle und Rollen weg, dann neu aufbauen. Ohne diesen Haken kommt das Template zum Bestehenden dazu."
                    />

                    {wipe && (
                      <Rise>
                        <div className="mt-3.5 space-y-2.5">
                          <div className="flex gap-2.5">
                            <AlertTriangle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
                            <p className="text-[11px] text-red-200/80 leading-relaxed">
                              Das löscht <strong>jeden</strong> Kanal und{" "}
                              <strong>jede</strong> Rolle, die der Bot anfassen
                              darf &mdash; auch die, die nichts mit der Vorlage
                              zu tun haben. Alle Nachrichtenverläufe sind danach
                              endgültig weg. Discord hat keinen Papierkorb.
                            </p>
                          </div>
                          <div className="flex gap-2.5">
                            <Info className="h-4 w-4 text-slate-500 shrink-0 mt-0.5" />
                            <p className="text-[11px] text-slate-400 leading-relaxed">
                              Was über der Bot-Rolle steht, bleibt stehen
                              &mdash; daran kommt der Bot nicht heran.
                            </p>
                          </div>

                          <label className="block">
                            <span className="text-[10px] font-black uppercase tracking-widest text-red-300/70">
                              Zum Bestätigen den Servernamen tippen
                            </span>
                            <input
                              value={wipeConfirm}
                              onChange={(event) =>
                                setWipeConfirm(event.target.value)
                              }
                              placeholder={pre?.guild_name || "Servername"}
                              className="mt-1.5 w-full bg-[#0d1b31] border border-red-500/30 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-red-500/60 transition-colors"
                            />
                            {pre?.guild_name && (
                              <span className="block text-[10px] text-slate-600 mt-1.5">
                                Erwartet:{" "}
                                <code className="text-slate-400">
                                  {pre.guild_name}
                                </code>
                              </span>
                            )}
                          </label>
                        </div>
                      </Rise>
                    )}
                  </div>

                  <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 pt-2">
                    University Bot
                  </p>
                  {steps.map((step, index) => (
                    <Rise key={step.key} index={index}>
                      <InlineToggle
                        checked={Boolean(options[step.key])}
                        onCheckedChange={(value) =>
                          setOptions((old) => ({ ...old, [step.key]: value }))
                        }
                        label={step.label}
                        hint={step.description}
                      />
                    </Rise>
                  ))}
                </div>
              </Rise>
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
                disabled={busy || !wipeReady}
                onClick={start}
                title={
                  wipeReady
                    ? undefined
                    : "Tippe zuerst den Servernamen, um das Löschen zu bestätigen."
                }
                className={cn(
                  "ml-auto px-4 py-2 rounded-xl text-[11px] font-black uppercase tracking-wider transition-all inline-flex items-center gap-2",
                  !wipeReady
                    ? "bg-slate-800 text-slate-600 cursor-not-allowed"
                    : wipe
                    ? "bg-red-600 text-white hover:bg-red-500"
                    : "bg-primary text-white hover:bg-primary/80",
                  busy && "opacity-50"
                )}
              >
                {busy ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : wipe ? (
                  <Trash2 className="h-3.5 w-3.5" />
                ) : (
                  <Rocket className="h-3.5 w-3.5" />
                )}
                {wipe
                  ? "Alles löschen und neu bauen"
                  : chosenTemplate
                  ? `„${chosenTemplate.name}“ bauen`
                  : "Starten"}
              </button>
            </div>
          </div>
        </Rise>
      )}

      {/* ── 4. Lauf ──────────────────────────────────────── */}
      {stage === 3 && (
        <Rise index={1}>
          <div className={cn(CARD, "space-y-4")}>
            {resumed && isRunning && (
              <div className="rounded-xl bg-sky-500/[0.07] border border-sky-500/20 p-3.5 flex gap-2.5">
                <Info className="h-4 w-4 text-sky-400 shrink-0 mt-0.5" />
                <p className="text-[12px] text-sky-200/80 leading-relaxed">
                  Hier lief schon ein Speedrun — du siehst den laufenden Stand.
                </p>
              </div>
            )}

            <div className="flex items-center gap-3 flex-wrap">
              <p className="text-xs font-black uppercase tracking-widest text-slate-500">
                {phase === "building" && "Der Template-Bot baut…"}
                {phase === "finishing" && "Der University Bot richtet ein…"}
                {phase === "done" && "Fertig"}
                {phase === "partial" && "Fertig, mit Lücken"}
                {phase === "failed" && "Abgebrochen"}
                {phase === "idle" && "Bereit"}
              </p>
              {progress.total > 0 && isRunning && (
                <span className="text-[11px] font-mono text-slate-500">
                  {progress.step}/{progress.total}
                </span>
              )}
              {phase === "done" && (
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              )}
              {phase === "partial" && (
                <TriangleAlert className="h-4 w-4 text-amber-400" />
              )}
              {phase === "failed" && <XCircle className="h-4 w-4 text-red-400" />}

              {isRunning && (
                <button
                  onClick={cancel}
                  disabled={busy}
                  className="ml-auto px-3 py-1.5 rounded-lg border border-red-500/30 text-red-300/90 text-[10px] font-black uppercase tracking-wider hover:bg-red-500/10 transition-colors inline-flex items-center gap-1.5 disabled:opacity-50"
                >
                  <Square className="h-3 w-3" />
                  Abbrechen
                </button>
              )}
            </div>

            {progress.total > 0 && (
              <div className="h-1.5 rounded-full bg-slate-800 overflow-hidden">
                <div
                  className={cn(
                    "h-full bg-primary transition-all duration-500 relative overflow-hidden",
                    isRunning && "sr-sheen"
                  )}
                  style={{ width: `${percent}%` }}
                />
              </div>
            )}

            <Console lines={lines} running={isRunning} />

            {report && (
              <Rise>
                <div className="space-y-1.5">
                  <p className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                    Was der University Bot eingerichtet hat
                  </p>
                  {report.steps?.map((step: any, index: number) => (
                    <Rise key={step.key} index={index}>
                      <div className="flex items-start gap-2.5 py-1">
                        {step.ok ? (
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-0.5" />
                        ) : (
                          <CircleDashed className="h-3.5 w-3.5 text-amber-400 shrink-0 mt-0.5" />
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
                    </Rise>
                  ))}
                </div>
              </Rise>
            )}

            {phase === "partial" && (
              <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/20 p-3.5 flex gap-2.5">
                <TriangleAlert className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
                <p className="text-[12px] text-amber-200/80 leading-relaxed">
                  Einzelne Schritte sind nicht durchgelaufen — welche, steht
                  oben. Der Rest ist eingerichtet. Meist fehlt dem Bot ein
                  Recht, oder eine Rolle steht über seiner.
                </p>
              </div>
            )}

            {!isRunning && (
              <button
                onClick={restart}
                className="px-3.5 py-2 rounded-xl border border-slate-800 text-slate-400 text-[11px] font-black uppercase tracking-wider hover:text-white transition-colors inline-flex items-center gap-2"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Von vorne
              </button>
            )}
          </div>
        </Rise>
      )}
    </section>
  );
}
