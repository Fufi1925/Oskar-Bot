import React from "react";
import { Github, Globe, MessageCircle, Users } from "lucide-react";
import { LegalPage, Section } from "@/components/legal-page";

export const metadata = {
  title: "Team",
  description: "Die Menschen hinter dem Bot.",
};

const SUPPORT =
  process.env.NEXT_PUBLIC_SUPPORT_INVITE || "https://discord.gg/MG3rYnUZJV";
const REPO = "https://github.com/Fufi1925/Oskar-Bot";

interface Member {
  name: string;
  role: string;
  description?: string;
  github?: string;
  discord?: string;
  website?: string;
}

/**
 * Team members.
 *
 * Kept as plain data so the list can be edited without touching any
 * markup. NEXT_PUBLIC_TEAM_JSON overrides it at deploy time, which is
 * handy when the same code runs for more than one community.
 */
const DEFAULT_TEAM: Member[] = [
  {
    name: "Fufi1925",
    role: "Maintainer",
    description:
      "Entwicklung, Betrieb und Support des Bots und des Dashboards.",
    github: "https://github.com/Fufi1925",
  },
];

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

export default function TeamPage() {
  const team = loadTeam();

  return (
    <LegalPage
      title="Team"
      subtitle="Die Menschen, die den Bot bauen und betreiben."
      icon={Users}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        {team.map((member) => (
          <div
            key={member.name}
            className="bg-white/[0.02] border border-white/[0.05] rounded-3xl p-7 hover:border-blue-500/25 transition-colors"
          >
            <div className="flex items-start gap-4">
              <div className="h-14 w-14 rounded-2xl bg-blue-500/15 border border-blue-500/25 flex items-center justify-center text-blue-300 font-black text-lg shrink-0">
                {initials(member.name)}
              </div>
              <div className="min-w-0">
                <h3 className="font-bold text-white text-lg truncate">
                  {member.name}
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

            {(member.github || member.discord || member.website) && (
              <div className="flex items-center gap-3 mt-5 pt-5 border-t border-white/[0.05]">
                {member.github && (
                  <a
                    href={member.github}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-slate-500 hover:text-blue-400 transition-colors"
                    aria-label={`${member.name} auf GitHub`}
                  >
                    <Github className="h-4 w-4" />
                  </a>
                )}
                {member.discord && (
                  <a
                    href={member.discord}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-slate-500 hover:text-blue-400 transition-colors"
                    aria-label={`${member.name} auf Discord`}
                  >
                    <MessageCircle className="h-4 w-4" />
                  </a>
                )}
                {member.website && (
                  <a
                    href={member.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-slate-500 hover:text-blue-400 transition-colors"
                    aria-label={`Website von ${member.name}`}
                  >
                    <Globe className="h-4 w-4" />
                  </a>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      <Section title="Mitmachen">
        <p>
          Das Projekt ist quelloffen. Fehlerberichte, Verbesserungsvorschläge
          und Pull Requests sind willkommen — auch kleine.
        </p>
        <p className="flex flex-wrap gap-x-6 gap-y-2 pt-2">
          <a
            href={REPO}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:underline"
          >
            Repository auf GitHub
          </a>
          <a
            href={SUPPORT}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:underline"
          >
            Support-Server
          </a>
        </p>
      </Section>
    </LegalPage>
  );
}
