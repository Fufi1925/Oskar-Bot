import React from "react";
import Link from "next/link";
import {
  ArrowRight, Globe, MessageCircle, Sparkles, Users, Video, Wrench, Shield,
} from "lucide-react";
import { LegalPage } from "@/components/legal-page";
import { SUPPORT_INVITE } from "@/lib/legal";

export const metadata = {
  title: "Team",
  description: "Die Menschen hinter dem Bot — und wie du dazukommst.",
};

// Rendered per request rather than at build time: the avatars are
// fetched from the running bot, which is not up while the image builds.
export const dynamic = "force-dynamic";

const SUPPORT = SUPPORT_INVITE;

const API_BASE_URL =
  process.env.API_BASE_URL ||
  `http://127.0.0.1:${process.env.PORT || 8080}/api/v1`;

/**
 * Die Team-Seite.
 *
 * ── Was an der alten Fassung nicht stimmte ──────────────────────────
 *
 * Vier Dinge, alle nachgemessen und nicht vermutet:
 *
 *   1. **Man kam von hier nicht ins Team.** Die Seite verlinkte die
 *      Bewerbung genau null Mal (`grep -c "team/apply"` → 0). Wer
 *      mitmachen wollte, musste im Navigationsmenü ein Aufklappmenü
 *      finden. Eine Seite, die „Team“ heißt, ist aber genau die, auf
 *      der jemand landet, der überlegt dazuzugehören.
 *   2. **Sie sah aus wie von einer anderen Website.** `bg-white/[0.02]`
 *      und `border-white/[0.05]` — der alte Glas-Stil, den das
 *      Dashboard längst hinter sich hat. Der Rest der Seite benutzt
 *      `#0f0f13` mit `border-slate-800`.
 *   3. **Unter jedem Namen stand eine 19-stellige Zahl.** Eine
 *      Discord-ID als Fließtext sagt einem Besucher nichts und lässt
 *      sich nicht anklicken. Jetzt ist sie ein Link auf das
 *      Discord-Profil — dasselbe Datum, aber benutzbar.
 *   4. **Kein Wort dazu, was das Team eigentlich tut.**
 *
 * ── Warum die offenen Rollen vom Bot kommen ─────────────────────────
 *
 * Sie stehen in `bot/utils/web_apply_store.py` und nirgends sonst.
 * Hier eine zweite Liste zu pflegen hieße: eine geschlossene Rolle
 * steht auf der Website weiter offen, und wer klickt, bekommt vom Bot
 * eine Absage. Genau das ist der Navigationsleiste passiert, die ihre
 * vier Rollen bis heute fest verdrahtet hat — ein Test hält dort
 * wenigstens die Schlüssel zusammen.
 *
 * Antwortet der Bot nicht, verschwindet der Abschnitt lieber ganz,
 * statt vier Rollen zu behaupten, die vielleicht zu sind.
 */

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
 * Note there are no source-code fields. The repository is private and
 * stays private -- a link to a 404 tells a visitor the project exists
 * under a particular account and invites them to go looking, which is
 * the opposite of the point.
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

interface OffeneRolle {
  key: string;
  label: string;
  short: string;
  colour: string;
  questions: number;
  open: boolean;
}

/** Ein Symbol je Rolle — vier farbige Punkte sagen weniger als vier Bilder. */
const ROLLEN_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  content: Video,
  designer: Sparkles,
  moderator: Shield,
  tester: Wrench,
};

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

/**
 * Welche Rollen gerade offen sind — vom Bot, nicht von hier.
 *
 * Bei jedem Fehler eine leere Liste: dann fällt der Abschnitt weg.
 * Das ist die ehrlichere Antwort als vier Rollen zu zeigen, von denen
 * womöglich keine offen ist — wer sich auf eine geschlossene bewirbt,
 * bekommt vom Bot eine Absage und weiß nicht, warum.
 */
async function loadRollen(): Promise<OffeneRolle[]> {
  try {
    const headers: Record<string, string> = {};
    const key = process.env.DASHBOARD_API_KEY || "";
    if (key) headers.Authorization = `Bearer ${key}`;

    const response = await fetch(`${API_BASE_URL}/webapply/roles`, {
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(4000),
    });
    if (!response.ok) return [];
    const data = await response.json();
    const rollen = data?.roles;
    return Array.isArray(rollen) ? rollen : [];
  } catch {
    return [];
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

const KARTE =
  "rounded-2xl border border-slate-800 bg-[#0f0f13] transition-colors";

/**
 * Ein Abschnitt im Stil dieser Seite.
 *
 * Warum nicht das gemeinsame `<Section>` aus `legal-page.tsx`: das
 * trägt noch `bg-white/[0.02]` mit `border-white/[0.05]` — den alten
 * Glas-Stil. Genau der war einer der Gründe, warum diese Seite wie von
 * einer anderen Website aussah.
 *
 * Und warum ich `<Section>` trotzdem nicht einfach umgestellt habe:
 * daran hängen noch Impressum, Datenschutz, Status und AGB. Deren
 * Aussehen mitzuändern, weil hier ein Reiter neu gemacht wird, wäre
 * eine Änderung an vier Seiten, die niemand bestellt hat. Der
 * Unterschied bleibt also vorerst sichtbar — das ist bewusst und
 * nicht übersehen.
 */
function Block({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-slate-800 bg-[#0f0f13] p-6 sm:p-7">
      <h2 className="mb-4 text-lg font-bold text-white">{title}</h2>
      <div className="space-y-3 text-[15px] leading-relaxed text-slate-400">
        {children}
      </div>
    </section>
  );
}

export default async function TeamPage() {
  const team = loadTeam();

  // Beide Anfragen nebeneinander. Nacheinander wäre die Seite doppelt
  // so lange am Laden, ohne dass eine auf die andere wartet.
  const [profiles, rollen] = await Promise.all([
    loadProfiles(team.map((member) => member.id).filter(Boolean)),
    loadRollen(),
  ]);

  const offen = rollen.filter((rolle) => rolle.open);

  return (
    <LegalPage
      title="Team"
      subtitle="Die Menschen, die den Bot bauen und betreiben — und wie du dazukommst."
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
              className={`${KARTE} p-6 hover:border-slate-700`}
            >
              <div className="flex items-start gap-4">
                {avatar ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={avatar}
                    alt={`Profilbild von ${name}`}
                    width={56}
                    height={56}
                    className="h-14 w-14 shrink-0 rounded-2xl border border-slate-800 object-cover"
                  />
                ) : (
                  // Initials, not a broken image: the bot may be
                  // restarting, and that should not leave a grey box.
                  <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-indigo-500/25 bg-indigo-500/10 text-lg font-black text-indigo-300">
                    {initials(name)}
                  </div>
                )}
                <div className="min-w-0">
                  <h3 className="truncate text-lg font-bold text-white">
                    {name}
                  </h3>
                  <p className="mt-0.5 text-[13px] font-semibold text-indigo-400">
                    {member.role}
                  </p>
                </div>
              </div>

              {member.description && (
                <p className="mt-5 text-[14px] leading-relaxed text-slate-400">
                  {member.description}
                </p>
              )}

              <div className="mt-5 flex items-center gap-3 border-t border-slate-800 pt-4">
                {/* Die Discord-ID als Link statt als Zahlenkolonne.
                    Vorher stand hier eine 19-stellige Zahl im Fließtext:
                    für einen Besucher ohne Bedeutung und nicht
                    anklickbar. Dasselbe Datum, nur benutzbar. */}
                <a
                  href={`https://discord.com/users/${member.id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-[13px] text-slate-500 transition-colors hover:text-indigo-400"
                  title={`Discord-Profil von ${name} (ID ${member.id})`}
                >
                  <MessageCircle className="h-4 w-4" />
                  Discord-Profil
                </a>
                {member.website && (
                  <a
                    href={member.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ml-auto text-slate-500 transition-colors hover:text-indigo-400"
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

      {/* ── Mitmachen ───────────────────────────────────────────────
          Der Abschnitt, der vorher ganz fehlte. Die Rollen kommen vom
          Bot; antwortet er nicht oder ist gerade keine offen, steht
          hier nichts — lieber nichts als eine Rolle, die zu ist. */}
      {offen.length > 0 && (
        <Block title="Mitmachen">
          <p>
            Das Team besteht aus zwei Leuten, und für ein paar Dinge suchen
            wir Verstärkung. Bewerben geht über die Website: Rolle wählen,
            Fragen beantworten, abschicken. Wir melden uns per
            Direktnachricht.
          </p>

          <div className="grid gap-3 pt-2 sm:grid-cols-2">
            {offen.map((rolle) => {
              const Icon = ROLLEN_ICON[rolle.key] || Users;
              return (
                <Link
                  key={rolle.key}
                  href={`/team/apply?rolle=${rolle.key}`}
                  className={`${KARTE} group flex items-start gap-3.5 p-4 hover:border-slate-700`}
                >
                  <span
                    className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl border"
                    style={{
                      // Die Farbe kommt aus dem Bot, damit Website und
                      // Discord-Panel dieselbe Rolle gleich einfärben.
                      borderColor: `${rolle.colour}40`,
                      backgroundColor: `${rolle.colour}1a`,
                      color: rolle.colour,
                    }}
                  >
                    <Icon className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5 text-[15px] font-bold text-white">
                      {rolle.label}
                      <ArrowRight className="h-3.5 w-3.5 shrink-0 text-slate-600 transition-transform group-hover:translate-x-0.5 group-hover:text-indigo-400" />
                    </span>
                    <span className="mt-1 block text-[13px] leading-relaxed text-slate-400">
                      {rolle.short}
                    </span>
                    <span className="mt-1.5 block text-[12px] text-slate-600">
                      {rolle.questions}{" "}
                      {rolle.questions === 1 ? "Frage" : "Fragen"}
                    </span>
                  </span>
                </Link>
              );
            })}
          </div>

          <p className="pt-2 text-[13px] text-slate-500">
            Du brauchst einen Discord-Account und musst angemeldet sein —
            sonst wüssten wir hinterher nicht, wem wir die Rolle geben
            sollen. Pro Person eine Bewerbung.
          </p>
        </Block>
      )}

      <Block title="Kontakt">
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
      </Block>
    </LegalPage>
  );
}
