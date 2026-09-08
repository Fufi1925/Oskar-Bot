"use client";

import React from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  ExternalLink,
  Headphones,
  LifeBuoy,
  Loader2,
  MessageCircle,
  Radio,
} from "lucide-react";
import { api } from "@/lib/api";

function ticketDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" });
}

export function AccountSupportPanel({ userId }: { userId: string }) {
  const [support, setSupport] = React.useState<any>(null);
  const [status, setStatus] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    let active = true;
    Promise.allSettled([
      api.getAccountSupport(userId),
      fetch("/api/status", { cache: "no-store" }).then((response) =>
        response.json(),
      ),
    ])
      .then(([tickets, live]) => {
        if (!active) return;
        if (tickets.status === "fulfilled") setSupport(tickets.value);
        if (live.status === "fulfilled" && live.value?.ok)
          setStatus(live.value.data);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [userId]);

  const invite = support?.support_invite || "https://discord.gg/F3TedBAVZT";
  const online = status?.state === "online" && status?.main?.bot_ready;
  const incident = status && (!online || status.maintenance);

  return (
    <section
      id="support"
      className="overflow-hidden rounded-2xl border border-slate-800 bg-[#131318]"
    >
      <div className="flex flex-col gap-4 border-b border-slate-800 px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div>
          <div className="flex items-center gap-2 text-sky-300">
            <LifeBuoy className="h-5 w-5" />
            <span className="text-xs font-bold uppercase tracking-[0.2em]">
              Support
            </span>
          </div>
          <h2 className="mt-2 text-xl font-bold text-white">
            Hilfe zu deinem Konto
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Tickets, bekannte Störungen und direkter Kontakt zum Support-Team.
          </p>
        </div>
        <a
          href={invite}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#5865f2] px-4 py-2.5 text-sm font-bold text-white hover:bg-[#4752c4]"
        >
          <MessageCircle className="h-4 w-4" />
          Neue Supportanfrage
        </a>
      </div>

      <div className="grid gap-px bg-slate-800 lg:grid-cols-[1.35fr_0.65fr]">
        <div className="bg-[#111116] p-5 sm:p-6">
          <h3 className="flex items-center gap-2 font-bold text-white">
            <Headphones className="h-4 w-4 text-sky-400" />
            Eigene offene Tickets
          </h3>
          {loading ? (
            <Loader2 className="mt-5 h-5 w-5 animate-spin text-sky-400" />
          ) : support?.tickets?.length ? (
            <div className="mt-4 space-y-2">
              {support.tickets.map((ticket: any) => (
                <a
                  key={ticket.channel_id}
                  href={ticket.url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-3 rounded-xl border border-slate-800 bg-black/20 p-3 hover:border-slate-700"
                >
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-sky-400/10 text-sm font-black text-sky-300">
                    #{ticket.ticket_number || "–"}
                  </span>
                  <span className="min-w-0 flex-1">
                    <strong className="block truncate text-sm text-slate-200">
                      {ticket.guild_name || `Server ${ticket.guild_id}`}
                    </strong>
                    <span className="mt-0.5 block text-xs text-slate-500">
                      {ticket.channel_name ? `#${ticket.channel_name} · ` : ""}
                      {ticketDate(ticket.created_at)}
                      {ticket.claimed ? " · übernommen" : ""}
                    </span>
                  </span>
                  <ExternalLink className="h-4 w-4 text-slate-600" />
                </a>
              ))}
            </div>
          ) : (
            <div className="mt-4 rounded-xl border border-slate-800 bg-black/20 p-4">
              <p className="flex items-center gap-2 text-sm text-slate-300">
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                Du hast derzeit keine offenen Tickets.
              </p>
              <p className="mt-2 text-xs leading-5 text-slate-600">
                Tickets werden auf Discord eröffnet und erscheinen hier
                automatisch.
              </p>
            </div>
          )}
        </div>

        <div className="bg-[#111116] p-5 sm:p-6">
          <h3 className="flex items-center gap-2 font-bold text-white">
            <Radio className="h-4 w-4 text-emerald-400" />
            Live-Status des Bots
          </h3>
          <div
            className={`mt-4 rounded-xl border p-4 ${online ? "border-emerald-500/20 bg-emerald-500/[0.05]" : incident ? "border-amber-500/25 bg-amber-500/[0.06]" : "border-slate-800 bg-black/20"}`}
          >
            <p
              className={`flex items-center gap-2 text-sm font-bold ${online ? "text-emerald-300" : incident ? "text-amber-300" : "text-slate-400"}`}
            >
              {online ? (
                <CheckCircle2 className="h-4 w-4" />
              ) : incident ? (
                <AlertTriangle className="h-4 w-4" />
              ) : (
                <Clock className="h-4 w-4" />
              )}
              {online
                ? "Alle Systeme laufen"
                : status?.maintenance
                  ? "Geplante Wartung"
                  : incident
                    ? "Bekannte Störung"
                    : "Status wird geprüft"}
            </p>
            <p className="mt-2 text-xs leading-5 text-slate-500">
              {status?.maintenance_note ||
                (online
                  ? "Der Bot ist erreichbar und mit Discord verbunden."
                  : incident
                    ? "Der Statusdienst meldet aktuell eine Einschränkung."
                    : "Der unabhängige Statusdienst ist gerade nicht erreichbar.")}
            </p>
          </div>
          <div className="mt-4 space-y-2">
            <Link
              href="/status"
              className="flex items-center justify-between rounded-lg border border-slate-800 px-3 py-2 text-sm text-slate-300 hover:border-slate-700"
            >
              Bekannte Störungen und Verlauf{" "}
              <ExternalLink className="h-3.5 w-3.5" />
            </Link>
            <a
              href={invite}
              target="_blank"
              rel="noreferrer"
              className="flex items-center justify-between rounded-lg border border-slate-800 px-3 py-2 text-sm text-slate-300 hover:border-slate-700"
            >
              Discord-Support öffnen <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
