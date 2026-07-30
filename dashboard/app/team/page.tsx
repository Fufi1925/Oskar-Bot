import React from "react";
import { Globe, MessageCircle, Users } from "lucide-react";
import { LegalPage, Section } from "@/components/legal-page";
import { SUPPORT_INVITE } from "@/lib/legal";

export const metadata = {
  title: "Team",
  description: "Die Menschen hinter dem Bot.",
};

// Rendered per request rather than at build time: the avatars are
// fetched from the running bot, which is not up while the image builds.
export const dynamic = "force-dynamic";

const SUPPORT = SUPPORT_INVITE;

const API_BASE_URL =
  process.env.API_BASE_URL ||
  `http://127.0.0.1:${process.env.PORT || 8080}/api/v1`;

interface Member {
  /** Discord id. Used for the avatar and as the profile link. */
  id: string;
  /** Fallback name, shown until the live one arrives. */
  name: string;
  role: string;
  description?: string;
  website?: string;
}

/**
 * The team.
 *
 * Kept as plain data so the list can be edited without touching markup.
 * NEXT_PUBLIC_TEAM_JSON overrides it at deploy time.
 *
 * Note there are no GitHub fields. The repository is private and stays
 * private -- a link to a 404 tells a visitor the project exists on
 * GitHub and invites them to go looking, which is the opposite of the
 * point.
 */
const DEFAULT_TEAM: Member[] = [
  {
    id: "1303627964734246944",
    name: "Fufi",
    role: "Entwickler & Betrieb",
    description:
      "Baut und betreibt den Bot und das Dashboard. Kümmert sich um " +
      "Updates, Störungen und den Support.",
  },
  {
    id: "1033826242270609449",
    name: "Vexo",
    role: "Entwickler · Template-Bot",
    description:
      "Von ihm stammt die ursprüngliche Idee zum Projekt. Entwickelt " +
      "den Template-Bot mit den fertigen Server-Vorlagen.",
  },
];

interface Profile {
  id: string;
  name: string | null;
  avatar: string | null;
}

/**
 * Real Discord names and avatars for the team.
 *
 * An avatar URL cannot be built from an id: the CDN path needs the
 * avatar hash, so only the bot can produce a working one. If the bot is
 * not reachable -- during a deploy, say -- this returns nothing and the
 * cards fall back to initials. A team page is not worth a 500.
 */
async function loadProfiles(ids: string[]): Promise<Record<string, Profile>> {
  try {
    const headers: Record<string, string> = {};
    const key = process.env.DASHBOARD_API_KEY || "";
    if (key) headers.Authorization = `Bearer ${key}`;

    const response = await fetch(
      `${API_BASE_URL}/bot/profiles?ids=${ids.join(",")}`,
      { headers, cache: "no-store", signal: AbortSignal.timeout(4000) }
    );
    if (!response.ok) return {};
    const data = await response.json();
    return data?.profiles || {};
  } catch {
    return {};
  }
}

function loadTeam(): Member[] {
  const raw = process.env.NEXT_PUBLIC_TEAM_JSON;
  if (!raw) return DEFAULT_TEAM;
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) && parsed.length ? parsed : DEFAULT_TEAM;
  } catch {
    // A malformed variable should not take the page down.
    return DEFAULT_TEAM;
  }
}

function initials(name: string) {
  return name
    .split(/[\s_-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

export default async function TeamPage() {
  const team = loadTeam();
  const profiles = await loadProfiles(
    team.map((member) => member.id).filter(Boolean)
  );

  return (
    <LegalPage
      title="Team"
      subtitle="Die Menschen, die den Bot bauen und betreiben."
      icon={Users}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        {team.map((member) => {
          const profile = profiles[member.id];
          const name = profile?.name || member.name;
          const avatar = profile?.avatar;

          return (
            <div
              key={member.id || member.name}
              className="bg-white/[0.02] border border-white/[0.05] rounded-3xl p-7 hover:border-blue-500/25 transition-colors"
            >
              <div className="flex items-start gap-4">
                {avatar ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={avatar}
                    alt={`Profilbild von ${name}`}
                    width={56}
                    height={56}
                    className="h-14 w-14 rounded-2xl border border-white/10 object-cover shrink-0"
                  />
                ) : (
                  // Initials, not a broken image: the bot may be
                  // restarting, and that should not leave a grey box.
                  <div className="h-14 w-14 rounded-2xl bg-blue-500/15 border border-blue-500/25 flex items-center justify-center text-blue-300 font-black text-lg shrink-0">
                    {initials(name)}
                  </div>
                )}
                <div className="min-w-0">
                  <h3 className="font-bold text-white text-lg truncate">
                    {name}
                  </h3>
                  <p className="text-[11px] font-black uppercase tracking-widest text-blue-400 mt-0.5">
                    {member.role}
                  </p>
                </div>
              </div>

              {member.description && (
                <p className="text-slate-400 text-sm leading-relaxed mt-5">
                  {member.description}
                </p>
              )}

              <div className="flex items-center gap-3 mt-5 pt-5 border-t border-white/[0.05]">
                <span
                  className="flex items-center gap-1.5 text-slate-500 text-xs"
                  title="Discord-ID"
                >
                  <MessageCircle className="h-4 w-4" />
                  <span className="font-mono">{member.id}</span>
                </span>
                {member.website && (
                  <a
                    href={member.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-slate-500 hover:text-blue-400 transition-colors ml-auto"
                    aria-label={`Website von ${name}`}
                  >
                    <Globe className="h-4 w-4" />
                  </a>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <Section title="Kontakt">
        <p>
          Fehler gefunden, Frage oder ein Vorschlag? Am schnellsten geht es
          über den Support-Server — dort sind wir beide erreichbar.
        </p>
        <p className="pt-2">
          <a
            href={SUPPORT}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:underline"
          >
            Support-Server beitreten
          </a>
        </p>
      </Section>
    </LegalPage>
  );
}
