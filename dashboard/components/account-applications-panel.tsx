"use client";

import React from "react";
import Link from "next/link";
import {
  CheckCircle2,
  Clock,
  ExternalLink,
  FileText,
  Loader2,
  MessageSquareText,
  Plus,
  XCircle,
} from "lucide-react";
import { api } from "@/lib/api";

const STATES: Record<string, { label: string; style: string; icon: any }> = {
  open: {
    label: "Offen",
    style: "border-amber-500/25 bg-amber-500/10 text-amber-300",
    icon: Clock,
  },
  accepted: {
    label: "Angenommen",
    style: "border-emerald-500/25 bg-emerald-500/10 text-emerald-300",
    icon: CheckCircle2,
  },
  denied: {
    label: "Abgelehnt",
    style: "border-rose-500/25 bg-rose-500/10 text-rose-300",
    icon: XCircle,
  },
  withdrawn: {
    label: "Zurückgezogen",
    style: "border-slate-700 bg-white/[0.03] text-slate-400",
    icon: XCircle,
  },
};

function date(value: number) {
  return value
    ? new Date(value * 1000).toLocaleDateString("de-DE", {
        day: "2-digit",
        month: "long",
        year: "numeric",
      })
    : "—";
}

export function AccountApplicationsPanel({ userId }: { userId: string }) {
  const [application, setApplication] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    let active = true;
    api
      .getMyApplication(userId)
      .then((data) => {
        if (active) setApplication(data?.application || null);
      })
      .catch((err: any) => {
        if (active)
          setError(err?.message || "Bewerbungsstatus nicht verfügbar.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [userId]);

  const state = STATES[application?.status] || STATES.open;
  const StateIcon = state.icon;

  return (
    <section
      id="bewerbungen"
      className="overflow-hidden rounded-2xl border border-slate-800 bg-[#131318]"
    >
      <div className="flex flex-col gap-4 border-b border-slate-800 px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div>
          <div className="flex items-center gap-2 text-violet-300">
            <FileText className="h-5 w-5" />
            <span className="text-xs font-bold uppercase tracking-[0.2em]">
              Bewerbungen
            </span>
          </div>
          <h2 className="mt-2 text-xl font-bold text-white">
            Deine Team-Bewerbung
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Status, Einreichungsdatum und Rückmeldung des Teams.
          </p>
        </div>
        <Link
          href="/team/apply"
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-violet-500"
        >
          <Plus className="h-4 w-4" />
          Neue Bewerbung starten
        </Link>
      </div>

      {loading ? (
        <div className="grid place-items-center p-10">
          <Loader2 className="h-5 w-5 animate-spin text-violet-400" />
        </div>
      ) : application ? (
        <div className="grid gap-px bg-slate-800 md:grid-cols-[0.75fr_1.25fr]">
          <div className="bg-[#111116] p-5 sm:p-6">
            <p className="text-xs font-semibold text-slate-600">
              Laufende oder letzte Bewerbung
            </p>
            <p className="mt-3 font-mono text-xl font-bold text-white">
              {application.ticket || `#${application.user_id}`}
            </p>
            <span
              className={`mt-3 inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-bold ${state.style}`}
            >
              <StateIcon className="h-3.5 w-3.5" />
              {state.label}
            </span>
            <dl className="mt-5 space-y-3 text-sm">
              <div>
                <dt className="text-xs text-slate-600">Rolle</dt>
                <dd className="mt-1 text-slate-300">
                  {application.role_label || application.role_key}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-600">Eingereicht am</dt>
                <dd className="mt-1 text-slate-300">
                  {date(application.created_at)}
                </dd>
              </div>
              {application.decided_at > 0 && (
                <div>
                  <dt className="text-xs text-slate-600">Entschieden am</dt>
                  <dd className="mt-1 text-slate-300">
                    {date(application.decided_at)}
                  </dd>
                </div>
              )}
            </dl>
          </div>
          <div className="bg-[#111116] p-5 sm:p-6">
            <h3 className="flex items-center gap-2 font-bold text-white">
              <MessageSquareText className="h-4 w-4 text-violet-400" />
              Entscheidung und Rückmeldung
            </h3>
            <p className="mt-4 text-sm leading-6 text-slate-400">
              {application.status === "open"
                ? "Deine Bewerbung wird derzeit vom Team geprüft. Eine Entscheidung erscheint automatisch hier."
                : application.reason ||
                  (application.status === "accepted"
                    ? "Deine Bewerbung wurde angenommen."
                    : application.status === "denied"
                      ? "Deine Bewerbung wurde abgelehnt."
                      : "Diese Bewerbung wurde zurückgezogen.")}
            </p>
            {application.reason && (
              <div className="mt-4 rounded-xl border border-slate-800 bg-black/20 p-4">
                <p className="text-xs font-bold uppercase tracking-wider text-slate-600">
                  Rückmeldung des Teams
                </p>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-300">
                  {application.reason}
                </p>
              </div>
            )}
            <Link
              href="/team/apply"
              className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-violet-300 hover:text-violet-200"
            >
              Bewerbung vollständig ansehen{" "}
              <ExternalLink className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      ) : (
        <div className="p-5 sm:p-6">
          <div className="rounded-xl border border-slate-800 bg-black/20 p-5">
            <p className="text-sm font-semibold text-slate-200">
              Keine Bewerbung vorhanden
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              Wähle eine offene Teamrolle aus und fülle den Fragebogen in Ruhe
              aus. Dein Entwurf wird lokal gespeichert.
            </p>
            <Link
              href="/team/apply"
              className="mt-4 inline-flex items-center gap-2 rounded-lg border border-violet-500/25 bg-violet-500/10 px-3 py-2 text-sm font-bold text-violet-300"
            >
              <Plus className="h-4 w-4" />
              Zur Bewerbungsseite
            </Link>
          </div>
        </div>
      )}
      {error && (
        <p className="border-t border-slate-800 px-5 py-3 text-sm text-rose-300 sm:px-6">
          {error}
        </p>
      )}
    </section>
  );
}
