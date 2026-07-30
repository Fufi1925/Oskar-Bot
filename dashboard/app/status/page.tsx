import React from "react";
import { Activity } from "lucide-react";
import { LegalPage, Section } from "@/components/legal-page";
import { BRAND, SUPPORT_INVITE } from "@/lib/legal";

export const metadata = {
  title: "Status",
  description: "Läuft der Bot gerade?",
};

// Never cached. A status page that shows a five minute old state is
// worse than none: it says "everything fine" during an outage.
export const dynamic = "force-dynamic";
export const revalidate = 0;

const STATUS_BOT_URL = (process.env.STATUS_BOT_URL || "").trim().replace(/\/$/, "");

interface StatusData {
  state: string;
  since: number;
  maintenance: boolean;
  maintenance_note: string;
  brand: string;
  main: {
    reachable: boolean;
    bot_ready: boolean;
    dashboard: string;
    latency_ms: number | null;
    status_code: number | null;
    error: string | null;
    checked_at: number;
  };
  uptime?: {
    known: boolean;
    percent?: number;
    days?: number;
    outage_count?: number;
    complete?: boolean;
  };
}

/**
 * Ask the status bot how things are.
 *
 * Deliberately the *status bot*, not the main bot: this page has to be
 * useful precisely when the main bot is down, and a page that asks the
 * broken thing whether it is broken always answers "fine" or nothing at
 * all.
 *
 * Returns null when the status service cannot be reached either, and
 * the page says so rather than guessing.
 */
async function load(): Promise<StatusData | null> {
  if (!STATUS_BOT_URL) return null;
  try {
    const response = await fetch(`${STATUS_BOT_URL}/status.json`, {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) return null;
    return (await response.json()) as StatusData;
  } catch {
    return null;
  }
}

function Dot({ tone }: { tone: "good" | "bad" | "warn" | "unknown" }) {
  const colour = {
    good: "bg-emerald-400",
    bad: "bg-red-400",
    warn: "bg-amber-400",
    unknown: "bg-slate-500",
  }[tone];
  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${colour}`} />;
}

function Row({
  tone,
  label,
  value,
}: {
  tone: "good" | "bad" | "warn" | "unknown";
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 border-b border-white/[0.05] last:border-0">
      <span className="flex items-center gap-3 text-slate-300">
        <Dot tone={tone} />
        {label}
      </span>
      <span className="text-sm text-slate-500 text-right">{value}</span>
    </div>
  );
}

export default async function StatusPage() {
  const data = await load();

  // Not reachable at all. Both the main bot and the watcher would have
  // to be down for this, or the page is misconfigured -- either way,
  // saying nothing is the honest answer.
  if (!data) {
    return (
      <LegalPage
        title="Status"
        subtitle="Läuft der Bot gerade?"
        icon={Activity}
      >
        <div className="rounded-3xl border border-slate-700/50 bg-white/[0.02] p-8">
          <p className="flex items-center gap-3 text-lg font-bold text-white">
            <Dot tone="unknown" />
            Status nicht abrufbar
          </p>
          <p className="text-slate-400 mt-3 leading-relaxed">
            Die Statusüberwachung antwortet gerade nicht. Das heißt nicht
            zwingend, dass der Bot ausgefallen ist — es kann auch der
            Wächter selbst sein.
          </p>
          <p className="text-slate-400 mt-2">
            Im{" "}
            <a
              href={SUPPORT_INVITE}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-400 hover:underline"
            >
              Support-Server
            </a>{" "}
            steht der aktuelle Stand.
          </p>
        </div>
      </LegalPage>
    );
  }

  const { state, main, uptime } = data;

  const headline = data.maintenance
    ? { tone: "warn" as const, text: "Geplante Wartung" }
    : state === "online"
      ? { tone: "good" as const, text: "Alle Systeme laufen" }
      : state === "starting"
        ? { tone: "warn" as const, text: "Startet gerade" }
        : { tone: "bad" as const, text: "Störung" };

  const explanation = data.maintenance
    ? "An dem Bot wird gerade gearbeitet. Kurze Ausfälle sind in dieser Zeit normal."
    : state === "online"
      ? "Der Bot ist erreichbar und bereit."
      : state === "starting"
        ? "Der Bot antwortet, ist aber noch nicht vollständig bereit. Nach einem Update dauert das ein bis zwei Minuten."
        : "Der Bot ist von außen nicht erreichbar. Das kann ein Neustart, ein fehlgeschlagenes Update oder eine Störung bei Discord sein.";

  return (
    <LegalPage title="Status" subtitle="Läuft der Bot gerade?" icon={Activity}>
      <div className="rounded-3xl border border-white/[0.06] bg-white/[0.02] p-8">
        <p className="flex items-center gap-3 text-2xl font-black text-white">
          <Dot tone={headline.tone} />
          {headline.text}
        </p>
        <p className="text-slate-400 mt-3 leading-relaxed">{explanation}</p>
        {data.maintenance && data.maintenance_note && (
          <p className="text-amber-200/80 mt-2 text-sm">
            Grund: {data.maintenance_note}
          </p>
        )}
      </div>

      <Section title={data.brand || BRAND}>
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] px-6">
          <Row
            tone={main.reachable ? "good" : "bad"}
            label="Erreichbar"
            value={
              main.reachable
                ? `HTTP ${main.status_code ?? "?"}`
                : main.error || "keine Antwort"
            }
          />
          {main.reachable && main.latency_ms !== null && (
            <Row
              tone={main.latency_ms < 2000 ? "good" : "warn"}
              label="Antwortzeit"
              value={`${main.latency_ms} ms`}
            />
          )}
          <Row
            // Not red when unreachable: we never got far enough to
            // check this, and red would claim we did.
            tone={
              !main.reachable ? "unknown" : main.bot_ready ? "good" : "warn"
            }
            label="Discord-Verbindung"
            value={
              !main.reachable
                ? "nicht geprüft"
                : main.bot_ready
                  ? "verbunden"
                  : "noch nicht bereit"
            }
          />
          <Row
            tone={
              !main.reachable
                ? "unknown"
                : main.dashboard === "online"
                  ? "good"
                  : "warn"
            }
            label="Dashboard"
            value={
              !main.reachable
                ? "nicht geprüft"
                : main.dashboard === "online"
                  ? "erreichbar"
                  : main.dashboard
            }
          />
        </div>
      </Section>

      {uptime?.known && (
        <Section title="Die letzten Tage">
          <p>
            <strong className="text-white">
              {uptime.percent?.toFixed(2)} % erreichbar
            </strong>{" "}
            {uptime.complete
              ? `in den letzten ${uptime.days} Tagen`
              : "seit Beginn der Aufzeichnung"}
            {uptime.outage_count
              ? ` · ${uptime.outage_count} Störung${uptime.outage_count === 1 ? "" : "en"}`
              : " · keine Störung"}
            .
          </p>
        </Section>
      )}

      <Section title="Woher kommen diese Angaben?">
        <p>
          Ein zweiter, unabhängiger Dienst prüft alle 30 Sekunden von außen,
          ob der Bot antwortet — aus einem eigenen Container, damit er einen
          Totalausfall überhaupt melden kann. Ein Wächter, der mit dem
          Überwachten zusammen abstürzt, meldet gar nichts.
        </p>
        <p>
          Eine einzelne fehlgeschlagene Prüfung gilt noch nicht als Störung.
          Erst nach drei Fehlversuchen in Folge — also gut anderthalb Minuten
          — steht hier &bdquo;Störung&ldquo;. Sonst würde jedes Update wie ein
          Absturz aussehen.
        </p>
      </Section>
    </LegalPage>
  );
}
