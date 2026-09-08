import type { Metadata } from "next";
import Link from "next/link";
import { readVerifyResult } from "@/lib/verification-oauth";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Sichere Verifizierung | University Bot",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

const copy = {
  success: {
    eyebrow: "VERIFIZIERUNG ABGESCHLOSSEN",
    title: "Du bist verifiziert!",
    text: "Deine Identität wurde bestätigt und die Verifiziert-Rolle wurde erfolgreich vergeben.",
    color: "#34d399",
    tint: "rgba(52,211,153,.13)",
  },
  denied: {
    eyebrow: "ZUGRIFF ABGELEHNT",
    title: "Verifizierung abgelehnt",
    text: "Du erfüllst die Verifizierungsanforderungen dieses Servers nicht. Weitere Informationen findest du in deiner Discord-DM.",
    color: "#fb7185",
    tint: "rgba(251,113,133,.13)",
  },
  error: {
    eyebrow: "VERIFIZIERUNG NICHT ABGESCHLOSSEN",
    title: "Das hat nicht funktioniert",
    text: "Die sichere Discord-Prüfung konnte nicht abgeschlossen werden. Starte sie erneut oder wende dich an das Serverteam.",
    color: "#fbbf24",
    tint: "rgba(251,191,36,.13)",
  },
};

export default async function VerifyResultPage({
  params,
  searchParams,
}: {
  params: Promise<{ guildId: string }>;
  searchParams: Promise<{ result?: string }>;
}) {
  const [{ guildId }, query] = await Promise.all([params, searchParams]);
  const outcome = query.result ? readVerifyResult(query.result) : null;
  const valid = outcome && outcome.guild_id === guildId;
  const status = valid ? outcome.status : "error";
  const content = copy[status];
  const guildName =
    valid && outcome.guild_name ? outcome.guild_name : "Discord-Server";
  const blocked =
    valid && outcome.blocked?.length
      ? outcome.blocked.map((item) => item.name).join(", ")
      : null;

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#070a12] px-4 py-20 text-white">
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(circle at 50% 28%, rgba(45,82,190,.22), transparent 38%), radial-gradient(circle at 12% 80%, rgba(31,55,126,.16), transparent 35%)",
        }}
      />
      <section className="relative w-full max-w-xl overflow-hidden rounded-[28px] border border-white/10 bg-[#0d1220]/95 p-6 shadow-2xl shadow-black/50 sm:p-10">
        <div className="mb-9 flex items-center gap-3 border-b border-white/10 pb-6">
          <img
            src="/icon-192.png"
            alt="University Bot"
            className="h-11 w-11 rounded-xl"
          />
          <div>
            <p className="font-bold tracking-tight">University Bot</p>
            <p className="text-xs text-slate-400">
              Sichere One-Click-Verifizierung
            </p>
          </div>
          <span className="ml-auto rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2.5 py-1 text-[10px] font-bold text-emerald-300">
            OAUTH2
          </span>
        </div>

        <div className="text-center">
          <div
            className="mx-auto mb-6 grid h-20 w-20 place-items-center rounded-full border"
            style={{
              color: content.color,
              background: content.tint,
              borderColor: `${content.color}55`,
            }}
          >
            {status === "success" ? (
              <svg
                viewBox="0 0 24 24"
                className="h-10 w-10"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
              >
                <path d="m5 12 4 4L19 6" />
              </svg>
            ) : (
              <svg
                viewBox="0 0 24 24"
                className="h-10 w-10"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
              >
                <path d="M12 3 3.7 6.5v5.2c0 4.6 3.5 8 8.3 9.3 4.8-1.3 8.3-4.7 8.3-9.3V6.5L12 3Z" />
                <path d="m9 9 6 6m0-6-6 6" />
              </svg>
            )}
          </div>
          <p
            className="mb-3 text-[11px] font-black tracking-[.2em]"
            style={{ color: content.color }}
          >
            {content.eyebrow}
          </p>
          <h1 className="text-3xl font-black tracking-tight sm:text-4xl">
            {content.title}
          </h1>
          <p className="mx-auto mt-4 max-w-md leading-7 text-slate-400">
            {content.text}
          </p>
        </div>

        <div className="mt-8 rounded-2xl border border-white/10 bg-white/[.035] p-4">
          <div className="flex items-center gap-3">
            {valid && outcome.guild_icon ? (
              <img
                src={outcome.guild_icon}
                alt=""
                className="h-10 w-10 rounded-xl"
              />
            ) : (
              <div className="grid h-10 w-10 place-items-center rounded-xl bg-blue-500/15 font-black text-blue-300">
                U
              </div>
            )}
            <div className="min-w-0">
              <p className="text-xs text-slate-500">Zielserver</p>
              <p className="truncate font-semibold">{guildName}</p>
            </div>
          </div>
          {blocked && (
            <div className="mt-4 border-t border-white/10 pt-4 text-sm">
              <span className="text-slate-500">Blacklist-Treffer:</span>{" "}
              <span className="font-semibold text-rose-300">{blocked}</span>
            </div>
          )}
        </div>

        {!valid && (
          <a
            href={`/api/verify/start?guild=${encodeURIComponent(guildId)}`}
            className="mt-6 block rounded-xl bg-blue-600 px-5 py-3.5 text-center font-bold transition hover:bg-blue-500"
          >
            Erneut mit Discord prüfen
          </a>
        )}
        <Link
          href="/"
          className="mt-5 block text-center text-sm text-slate-500 transition hover:text-slate-300"
        >
          Zur University-Bot-Website
        </Link>
        <p className="mt-8 text-center text-[11px] leading-5 text-slate-600">
          Es werden nur deine Discord-Identität und Servermitgliedschaften
          gelesen. OAuth-Tokens und Serverlisten werden nicht gespeichert.
        </p>
      </section>
    </main>
  );
}
