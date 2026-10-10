"use client";

import React from "react";
import Link from "next/link";
import { createPortal } from "react-dom";
import {
  ArrowUpRight,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Eye,
  FileText,
  LifeBuoy,
  LockKeyhole,
  Loader2,
  MessageSquare,
  RefreshCw,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Star,
  Terminal,
  X,
  type LucideIcon,
} from "lucide-react";
import { websiteLocale, useWebsiteLocale } from "@/lib/i18n/locale";
import { useLanguage } from "@/lib/i18n/LanguageContext";
import { translateWebsiteText } from "@/lib/i18n/dom-translations";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  SecurityCard,
  SecurityMetrics,
  SecurityTabs,
} from "@/components/dashboard/security-workspace";

const STATUS: Record<string, { label: string; order: number }> = {
  pending: { label: "Entscheidung offen", order: 0 },
  accepted: { label: "Zugriff aktiv", order: 1 },
  declined: { label: "Abgelehnt", order: 2 },
  closed: { label: "Geschlossen", order: 3 },
};

const QUESTIONS = [
  {
    question: "CloudTIX reagiert nicht. Was kann ich prüfen?",
    answer:
      "Prüfe, ob der Bot auf deinem Server ist und das gewünschte Modul eingeschaltet ist. In den Kanalrechten muss CloudTIX den Kanal sehen und Nachrichten senden dürfen. Für Rollenaktionen muss die Bot-Rolle über der zu vergebenden Rolle stehen.",
    tab: "settings",
    link: "Servereinstellungen öffnen",
  },
  {
    question: "Warum fehlt ein Server in meiner Serverliste?",
    answer:
      "Du brauchst dort „Server verwalten“, Administratorrechte oder eine Dashboard-Freigabe. Prüfe auch, ob du mit dem richtigen Discord-Konto angemeldet bist. Server ohne CloudTIX können in der Liste direkt zur Bot-Einladung geöffnet werden.",
    href: "/dashboard/guilds",
    link: "Deine Server ansehen",
  },
  {
    question: "Warum fehlen Kanäle oder Rollen in der Auswahl?",
    answer:
      "CloudTIX muss die Kanäle sehen können. Nicht jedes Modul unterstützt jeden Kanaltyp. Prüfe die Rechte auf Discord und aktualisiere den Status im Serverkopf. Rollen, die über der Bot-Rolle stehen, kann der Bot nicht vergeben.",
    tab: "settings",
    link: "Einstellungen prüfen",
  },
  {
    question: "Meine Änderungen werden nicht gespeichert. Was jetzt?",
    answer:
      "Beachte die Fehlermeldung beim Speichern und prüfe die markierten Werte. Manche Funktionen benötigen Premium oder zusätzliche Bot-Rechte. Speichere oder verwirf offene Änderungen, bevor du den Tab wechselst.",
    tab: "logging",
    link: "Bot-Logs öffnen",
  },
  {
    question: "Warum greift AutoMod bei manchen Mitgliedern nicht?",
    answer:
      "Serverinhaber und Mitglieder mit „Administrator“ oder „Nachrichten verwalten“ sind automatisch ausgenommen. Prüfe außerdem die Rollen- und Kanal-Ausnahmen sowie den Hauptschalter im AutoMod-Tab. Der Live-Status zeigt die gespeicherte Konfiguration.",
    tab: "automod",
    link: "AutoMod öffnen",
  },
  {
    question: "Wie erhalte ich persönliche Hilfe?",
    answer:
      "Öffne unseren Discord-Support und beschreibe das Problem mit Server-ID, betroffenem Modul und Fehlermeldung. Wenn ein Supporter eine Dashboard-Freigabe benötigt, erscheint seine Anfrage unter „Supportfälle“. Der Serverinhaber kann sie prüfen und annehmen oder ablehnen.",
  },
  {
    question: "Wie beende ich einen Support-Zugriff?",
    answer:
      "Öffne unter „Supportfälle“ den aktiven Fall und wähle „Zugriff beenden“. Nach deiner Bewertung von 1 bis 10 wird der Fall geschlossen und der durch diesen Supportfall erteilte Dashboard-Zugriff sofort entzogen.",
  },
];

function zeit(value: number) {
  return value ? new Date(value * 1000).toLocaleString(websiteLocale()) : "—";
}

function SupportDialog({
  title,
  description,
  icon: Icon,
  busy,
  onClose,
  children,
}: {
  title: string;
  description: React.ReactNode;
  icon: LucideIcon;
  busy: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const titleId = React.useId();
  const descriptionId = React.useId();
  const closeRef = React.useRef(onClose);
  const busyRef = React.useRef(busy);
  closeRef.current = onClose;
  busyRef.current = busy;
  React.useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    ref.current?.focus();
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        if (!busyRef.current) closeRef.current();
      }
      if (event.key !== "Tab" || !ref.current) return;
      const controls = Array.from(
        ref.current.querySelectorAll<HTMLElement>(
          "button:not(:disabled), textarea:not(:disabled), input:not(:disabled), a[href]",
        ),
      );
      const first = controls[0],
        last = controls[controls.length - 1];
      if (!first) {
        event.preventDefault();
        ref.current.focus();
        return;
      }
      if (
        event.shiftKey &&
        (document.activeElement === first ||
          document.activeElement === ref.current)
      ) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === last ||
          document.activeElement === ref.current)
      ) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", keyboard);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", keyboard);
      previous?.focus();
    };
  }, []);
  if (typeof document === "undefined") return null;
  return createPortal(
    <div className="cloudtix-help-dialog-backdrop">
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        tabIndex={-1}
        className="cloudtix-help-dialog"
      >
        <header>
          <span>
            <Icon size={23} />
          </span>
          <button
            type="button"
            disabled={busy}
            onClick={onClose}
            aria-label="Dialog schließen"
          >
            <X size={19} />
          </button>
        </header>
        <h2 id={titleId}>{title}</h2>
        <div id={descriptionId} className="cloudtix-help-dialog-description">
          {description}
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}

export function GuildSupportPanel({
  guildId,
  supportUrl,
}: {
  guildId: string;
  supportUrl: string;
}) {
  useWebsiteLocale();
  const { language } = useLanguage();
  const [cases, setCases] = React.useState<any[]>([]);
  const [owner, setOwner] = React.useState<boolean | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<number | null>(null);
  const [view, setView] = React.useState("help");
  const [query, setQuery] = React.useState("");
  const [caseFilter, setCaseFilter] = React.useState("open");
  const [expanded, setExpanded] = React.useState<number | null>(null);
  const [messages, setMessages] = React.useState<Record<number, string>>({});
  const [decision, setDecision] = React.useState<{
    id: number;
    type: "accepted" | "declined";
  } | null>(null);
  const [acceptedName, setAcceptedName] = React.useState("");
  const [closeId, setCloseId] = React.useState<number | null>(null);
  const [rating, setRating] = React.useState(0);
  const [ratingNote, setRatingNote] = React.useState("");
  const loadVersion = React.useRef(0);

  const laden = React.useCallback(async () => {
    const version = ++loadVersion.current;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getGuildSupportCases(guildId);
      if (version !== loadVersion.current) return;
      setCases(data.cases || []);
      setOwner(true);
    } catch (error: any) {
      if (version !== loadVersion.current) return;
      if (error?.status === 403) {
        setOwner(false);
        setCases([]);
      } else
        setError(
          error?.message || "Supportfälle konnten nicht geladen werden.",
        );
    } finally {
      if (version === loadVersion.current) setLoading(false);
    }
  }, [guildId]);

  React.useEffect(() => {
    setCases([]);
    setOwner(null);
    setDecision(null);
    setAcceptedName("");
    setCloseId(null);
    setMessages({});
    setExpanded(null);
    void laden();
    return () => {
      loadVersion.current++;
    };
  }, [laden]);

  const antworten = async () => {
    if (!decision || busy !== null) return;
    const target = cases.find((fall) => fall.id === decision.id);
    setBusy(decision.id);
    try {
      await api.respondGuildSupportCase(guildId, decision.id, decision.type);
      if (decision.type === "accepted")
        setAcceptedName(target?.supporter_name || "Der Supporter");
      else toast.success("Die Support-Anfrage wurde abgelehnt.");
      setDecision(null);
      await laden();
    } catch (error: any) {
      toast.error(error?.message || "Aktion fehlgeschlagen.");
    } finally {
      setBusy(null);
    }
  };

  const schliessen = async () => {
    if (closeId === null || rating < 1 || busy !== null) return;
    setBusy(closeId);
    try {
      await api.closeGuildSupportCase(guildId, closeId, rating, ratingNote);
      toast.success(
        "Supportfall geschlossen. Der Support-Zugriff wurde entzogen.",
      );
      setCloseId(null);
      setRating(0);
      setRatingNote("");
      await laden();
    } catch (error: any) {
      toast.error(
        error?.message || "Supportfall konnte nicht geschlossen werden.",
      );
    } finally {
      setBusy(null);
    }
  };

  const senden = async (caseId: number) => {
    const message = (messages[caseId] || "").trim();
    if (!message || busy !== null) return;
    setBusy(caseId);
    try {
      await api.addGuildSupportMessage(guildId, caseId, message);
      setMessages((old) => ({ ...old, [caseId]: "" }));
      toast.success("Nachricht gesendet.");
      await laden();
    } catch (error: any) {
      toast.error(error?.message || "Nachricht konnte nicht gesendet werden.");
    } finally {
      setBusy(null);
    }
  };

  const pendingCount = cases.filter((fall) => fall.status === "pending").length;
  const activeCount = cases.filter((fall) => fall.status === "accepted").length;
  const closedCount = cases.filter((fall) => fall.status === "closed").length;
  const shownCases = cases
    .filter(
      (fall) =>
        caseFilter === "all" ||
        (caseFilter === "open"
          ? ["pending", "accepted"].includes(fall.status)
          : ["declined", "closed"].includes(fall.status)),
    )
    .sort(
      (a, b) =>
        (STATUS[a.status]?.order ?? 4) - (STATUS[b.status]?.order ?? 4) ||
        Number(b.updated_at || 0) - Number(a.updated_at || 0),
    );
  const needle = query.trim().toLocaleLowerCase();
  const questions = QUESTIONS.filter((item) =>
    `${item.question} ${item.answer} ${translateWebsiteText(item.question, language)} ${translateWebsiteText(item.answer, language)}`
      .toLocaleLowerCase()
      .includes(needle),
  );
  const root = `/dashboard/guild/${guildId}`;

  return (
    <section className="cloudtix-settings-page cloudtix-help-page">
      <header className="cloudtix-settings-heading">
        <div>
          <p className="cloudtix-workspace-eyebrow">DEIN SERVER / HILFE</p>
          <h1>Hilfe & Support</h1>
          <p>
            Finde Antworten, richte deinen Server ein und behalte persönliche
            Support-Freigaben im Blick.
          </p>
        </div>
        <a
          href={supportUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="cloudtix-workspace-action"
        >
          <MessageSquare size={16} />
          Discord-Support
          <ArrowUpRight size={14} />
        </a>
      </header>
      <SecurityTabs
        value={view}
        onChange={setView}
        label="Hilfe-Bereiche"
        items={[
          ["help", "Start & Antworten", LifeBuoy],
          [
            "cases",
            pendingCount
              ? `Supportfälle (${pendingCount} offen)`
              : "Supportfälle",
            ShieldCheck,
          ],
        ]}
      />
      <div hidden={view !== "help"} className="cloudtix-help-layout">
        <div className="space-y-5">
          <SecurityCard
            icon={BookOpen}
            title="Direkt zum richtigen Bereich"
            subtitle="Die wichtigsten Anlaufstellen für deinen Server."
          >
            <div className="cloudtix-help-quicklinks">
              {[
                {
                  title: "Dokumentation",
                  description: "Module und Einrichtung verständlich erklärt.",
                  href: "/docs",
                  icon: BookOpen,
                },
                {
                  title: "Befehle",
                  description: "Finde den passenden CloudTIX-Befehl.",
                  href: "/commands",
                  icon: Terminal,
                },
                {
                  title: "Servereinstellungen",
                  description: "Grundlagen und Bot-Konfiguration verwalten.",
                  href: `${root}/settings`,
                  icon: Settings2,
                },
                {
                  title: "Bot-Logs",
                  description: "Protokolle und Log-Kanäle konfigurieren.",
                  href: `${root}/logging`,
                  icon: FileText,
                },
              ].map((item) => (
                <Link key={item.href} href={item.href}>
                  <item.icon size={18} />
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.description}</p>
                  </div>
                  <ArrowUpRight size={14} />
                </Link>
              ))}
            </div>
          </SecurityCard>
          <SecurityCard
            icon={Settings2}
            title="Dein Einstieg in CloudTIX"
            subtitle="Drei Schritte, die dir bei der Einrichtung helfen."
          >
            <ol className="cloudtix-help-steps">
              <li>
                <span>01</span>
                <div>
                  <h3>Rechte prüfen</h3>
                  <p>
                    CloudTIX muss die gewünschten Kanäle sehen und für seine
                    Aufgaben die passenden Discord-Rechte haben.
                  </p>
                </div>
              </li>
              <li>
                <span>02</span>
                <div>
                  <h3>Module einrichten</h3>
                  <p>
                    Öffne einen Tab in der Sidebar, aktiviere das Modul und
                    passe seine Einstellungen an.
                  </p>
                  <Link href={`${root}/automod`}>
                    Mit AutoMod starten
                    <ArrowUpRight size={12} />
                  </Link>
                </div>
              </li>
              <li>
                <span>03</span>
                <div>
                  <h3>Speichern & nachvollziehen</h3>
                  <p>
                    Speichere deine Änderungen. Prüfe bei Problemen die
                    angezeigten Hinweise und die Bot-Logs.
                  </p>
                </div>
              </li>
            </ol>
          </SecurityCard>
          <div className="cloudtix-help-contact">
            <LifeBuoy size={25} />
            <h2>Noch keine Lösung gefunden?</h2>
            <p>
              Schicke uns im Discord-Support die Server-ID, das betroffene Modul
              und die Fehlermeldung. So können wir das Problem schneller
              einordnen.
            </p>
            <div>
              <span>Server-ID</span>
              <code>{guildId}</code>
              <button
                type="button"
                aria-label="Server-ID kopieren"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(guildId);
                    toast.success("Server-ID kopiert.");
                  } catch {
                    toast.error(
                      "Kopieren nicht möglich. Du kannst die Server-ID markieren.",
                    );
                  }
                }}
              >
                Kopieren
              </button>
            </div>
            <a
              href={supportUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="cloudtix-workspace-action is-secondary"
            >
              Support öffnen
              <ArrowUpRight size={14} />
            </a>
          </div>
        </div>
        <SecurityCard
          icon={MessageSquare}
          title="Häufige Fragen"
          subtitle="Antworten auf typische Fragen zu Einrichtung und Zugriff."
        >
          <div className="cloudtix-settings-search">
            <Search size={16} />
            <input
              aria-label="Hilfe durchsuchen"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Frage oder Stichwort suchen …"
              className="cloudtix-security-input"
            />
          </div>
          <div className="cloudtix-help-faq">
            {questions.map((item) => (
              <details key={item.question} open={needle ? true : undefined}>
                <summary>
                  {item.question}
                  <ChevronDown size={16} />
                </summary>
                <div>
                  <p>{item.answer}</p>
                  {item.link && (
                    <Link href={item.href || `${root}/${item.tab}`}>
                      {item.link}
                      <ArrowUpRight size={12} />
                    </Link>
                  )}
                </div>
              </details>
            ))}
          </div>
          {!questions.length && (
            <div className="cloudtix-settings-empty">
              <Search size={25} />
              <h3>Keine passende Antwort</h3>
              <p>
                Probiere ein anderes Stichwort oder öffne den Discord-Support.
              </p>
              <button
                type="button"
                onClick={() => setQuery("")}
                className="cloudtix-security-text-button"
              >
                Suche zurücksetzen
              </button>
            </div>
          )}
        </SecurityCard>
      </div>
      <div hidden={view !== "cases"} className="space-y-6">
        <SecurityMetrics
          items={[
            {
              label: "Offene Anfragen",
              value: owner ? pendingCount : "—",
              icon: Clock3,
              note: "Warten auf deine Entscheidung",
            },
            {
              label: "Aktive Supportfälle",
              value: owner ? activeCount : "—",
              icon: Eye,
              note: "Temporärer Dashboard-Zugriff",
            },
            {
              label: "Abgeschlossene Fälle",
              value: owner ? closedCount : "—",
              icon: CheckCircle2,
              note: "Geschlossen und Zugriff entzogen",
            },
          ]}
        />
        <div className="cloudtix-help-case-toolbar">
          <div>
            <h2>Deine Supportfälle</h2>
            <p>Offene Entscheidungen stehen zuerst.</p>
          </div>
          <div className="cloudtix-security-button-row">
            <div
              className="cloudtix-workspace-segmented"
              aria-label="Supportfälle filtern"
            >
              {[
                ["open", "Offen"],
                ["history", "Verlauf"],
                ["all", "Alle"],
              ].map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  aria-pressed={caseFilter === id}
                  onClick={() => setCaseFilter(id)}
                >
                  {label}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="cloudtix-settings-icon-button"
              onClick={() => void laden()}
              disabled={loading || busy !== null}
              aria-label="Supportfälle aktualisieren"
            >
              <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </div>
        {loading ? (
          <div role="status" className="cloudtix-settings-empty">
            <Loader2 size={25} className="animate-spin" />
            <p>Supportfälle werden geladen …</p>
          </div>
        ) : error ? (
          <SecurityCard
            icon={LifeBuoy}
            title="Supportfälle konnten nicht geladen werden"
          >
            <p className="cloudtix-security-note">{error}</p>
            <button
              type="button"
              onClick={() => void laden()}
              className="cloudtix-workspace-action is-secondary"
            >
              Erneut laden
            </button>
          </SecurityCard>
        ) : owner === false ? (
          <div className="cloudtix-help-restricted">
            <LockKeyhole size={25} />
            <h2>Support-Freigaben sind Sache des Serverinhabers</h2>
            <p>
              Du kannst die Hilfe und den Discord-Support nutzen. Supportfälle
              und Freigaben werden vom Serverinhaber verwaltet.
            </p>
          </div>
        ) : !shownCases.length ? (
          <div className="cloudtix-settings-card cloudtix-settings-empty">
            <ShieldCheck size={29} />
            <h3>
              {caseFilter === "history"
                ? "Noch kein Verlauf"
                : "Keine offenen Supportfälle"}
            </h3>
            <p>
              {caseFilter === "history"
                ? "Abgeschlossene und abgelehnte Fälle erscheinen hier."
                : "Neue Anfragen des Support-Teams erscheinen hier zur Prüfung."}
            </p>
          </div>
        ) : (
          <div className="cloudtix-help-cases">
            {shownCases.map((fall) => {
              const status = STATUS[fall.status];
              const isOpen = ["pending", "accepted"].includes(fall.status);
              const detailsOpen = expanded === fall.id;
              return (
                <article
                  key={fall.id}
                  className="cloudtix-help-case"
                  data-status={fall.status}
                >
                  <header>
                    {fall.supporter_avatar ? (
                      <img src={fall.supporter_avatar} alt="" />
                    ) : (
                      <span className="cloudtix-help-supporter-avatar">
                        <LifeBuoy size={20} />
                      </span>
                    )}
                    <div>
                      <h3>
                        {fall.supporter_name || `Discord ${fall.supporter_id}`}
                      </h3>
                      <p>
                        {fall.supporter_role || "Support-Team"} · Fall #
                        {fall.id}
                      </p>
                    </div>
                    <span className="cloudtix-help-case-status">
                      {status?.label || "Status unbekannt"}
                    </span>
                  </header>
                  <div className="cloudtix-help-case-content">
                    <p>
                      {fall.problem ||
                        "Der Supporter möchte dir bei einem Problem auf diesem Server helfen."}
                    </p>
                    <div className="cloudtix-help-case-meta">
                      <span>Angefragt: {zeit(fall.created_at)}</span>
                      <span>Aktualisiert: {zeit(fall.updated_at)}</span>
                      {fall.status === "closed" && fall.rating > 0 && (
                        <span>
                          <Star size={12} />
                          {fall.rating}/10
                        </span>
                      )}
                    </div>
                  </div>
                  <footer>
                    <button
                      type="button"
                      aria-expanded={detailsOpen}
                      aria-controls={`support-case-${fall.id}`}
                      onClick={() => setExpanded(detailsOpen ? null : fall.id)}
                      className="cloudtix-workspace-action is-secondary"
                    >
                      <MessageSquare size={14} />
                      Nachrichten ({fall.messages?.length || 0})
                      <ChevronDown
                        size={13}
                        className={detailsOpen ? "rotate-180" : ""}
                      />
                    </button>
                    <div className="cloudtix-security-button-row">
                      {fall.status === "pending" && (
                        <>
                          <button
                            type="button"
                            disabled={busy !== null}
                            onClick={() =>
                              setDecision({ id: fall.id, type: "declined" })
                            }
                            className="cloudtix-workspace-action is-secondary"
                          >
                            Ablehnen
                          </button>
                          <button
                            type="button"
                            disabled={busy !== null}
                            onClick={() =>
                              setDecision({ id: fall.id, type: "accepted" })
                            }
                            className="cloudtix-workspace-action"
                          >
                            <Check size={14} />
                            Annehmen
                          </button>
                        </>
                      )}
                      {fall.status === "accepted" && (
                        <button
                          type="button"
                          disabled={busy !== null}
                          onClick={() => {
                            setCloseId(fall.id);
                            setRating(0);
                            setRatingNote("");
                          }}
                          className="cloudtix-workspace-action is-secondary"
                        >
                          <LockKeyhole size={14} />
                          Zugriff beenden
                        </button>
                      )}
                    </div>
                  </footer>
                  <div
                    hidden={!detailsOpen}
                    id={`support-case-${fall.id}`}
                    className="cloudtix-help-case-thread"
                  >
                    {fall.messages?.length ? (
                      fall.messages.map((entry: any) => (
                        <div key={entry.id} className="cloudtix-help-message">
                          <header>
                            <strong>
                              {entry.actor_name ||
                                entry.actor_role ||
                                "Support"}
                            </strong>
                            <time>{zeit(entry.created_at)}</time>
                          </header>
                          <small>{entry.actor_role}</small>
                          <p>{entry.message}</p>
                        </div>
                      ))
                    ) : (
                      <p className="cloudtix-security-note">
                        Noch keine Nachrichten in diesem Fall.
                      </p>
                    )}
                    {fall.status === "closed" && fall.rating_note && (
                      <div className="cloudtix-help-message">
                        <strong>Dein Feedback</strong>
                        <p>{fall.rating_note}</p>
                      </div>
                    )}
                    {isOpen && (
                      <form
                        onSubmit={(e) => {
                          e.preventDefault();
                          void senden(fall.id);
                        }}
                        className="cloudtix-help-reply"
                      >
                        <label htmlFor={`support-reply-${fall.id}`}>
                          Nachricht an das Support-Team
                        </label>
                        <textarea
                          id={`support-reply-${fall.id}`}
                          className="cloudtix-security-input"
                          rows={3}
                          maxLength={2000}
                          disabled={busy !== null}
                          value={messages[fall.id] || ""}
                          onChange={(e) =>
                            setMessages((old) => ({
                              ...old,
                              [fall.id]: e.target.value,
                            }))
                          }
                          placeholder="Beschreibe das Problem oder ergänze weitere Informationen …"
                        />
                        <div>
                          <small>{(messages[fall.id] || "").length}/2000</small>
                          <button
                            type="submit"
                            disabled={
                              busy !== null || !(messages[fall.id] || "").trim()
                            }
                            className="cloudtix-workspace-action"
                          >
                            {busy === fall.id ? (
                              <Loader2 size={14} className="animate-spin" />
                            ) : (
                              <Send size={14} />
                            )}
                            Senden
                          </button>
                        </div>
                      </form>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
        <div className="cloudtix-settings-grid">
          <SecurityCard
            icon={ShieldCheck}
            title="Du kontrollierst die Freigabe"
            subtitle="Der Serverinhaber prüft und beantwortet Support-Anfragen."
          >
            <ol className="cloudtix-help-steps">
              <li>
                <span>01</span>
                <div>
                  <h3>Anfrage prüfen</h3>
                  <p>
                    Name, Rolle und Nachrichten des Supporters zeigen dir, worum
                    es geht.
                  </p>
                </div>
              </li>
              <li>
                <span>02</span>
                <div>
                  <h3>Bewusst entscheiden</h3>
                  <p>
                    Mit „Annehmen“ erteilst du den Zugriff für diesen Fall. Eine
                    Ablehnung erteilt keine Freigabe.
                  </p>
                </div>
              </li>
              <li>
                <span>03</span>
                <div>
                  <h3>Zugriff beenden</h3>
                  <p>
                    Schließe den Fall, wenn die Hilfe beendet ist. Die
                    Support-Freigabe endet sofort.
                  </p>
                </div>
              </li>
            </ol>
          </SecurityCard>
          <SecurityCard icon={LockKeyhole} title="Was die Freigabe bedeutet">
            <ul className="cloudtix-help-access">
              <li>
                <Check size={15} />
                <div>
                  <strong>Server-Dashboard & Diagnosen</strong>
                  <p>
                    Der zugewiesene Supporter kann die Servereinstellungen
                    einsehen und Probleme untersuchen.
                  </p>
                </div>
              </li>
              <li>
                <Check size={15} />
                <div>
                  <strong>Scans ändern nichts automatisch</strong>
                  <p>
                    Diagnosen prüfen beispielsweise Bot-Rechte, Rollen und
                    Verbindungen.
                  </p>
                </div>
              </li>
              <li>
                <LockKeyhole size={15} />
                <div>
                  <strong>Geschützte Inhaber-Bereiche</strong>
                  <p>
                    Die Vergabe von Dashboard-Zugriff und Inhaber-Bereiche
                    bleiben geschützt.
                  </p>
                </div>
              </li>
            </ul>
            <p className="cloudtix-security-note">
              Eine Support-Freigabe vergibt keine Discord-Rolle.
            </p>
          </SecurityCard>
        </div>
      </div>
      {decision && (
        <SupportDialog
          icon={decision.type === "accepted" ? ShieldCheck : X}
          title={
            decision.type === "accepted"
              ? "Support-Zugriff freigeben?"
              : "Anfrage ablehnen?"
          }
          description={
            decision.type === "accepted" ? (
              <p>
                <strong>
                  {cases.find((fall) => fall.id === decision.id)
                    ?.supporter_name || "Der Supporter"}
                </strong>{" "}
                erhält für diesen Fall Zugriff auf dein Server-Dashboard und
                kann Einstellungen prüfen sowie Diagnosen ausführen. Du kannst
                die Freigabe durch Schließen des Falls beenden.
              </p>
            ) : (
              <p>
                Der Supporter erhält durch diese Anfrage keinen
                Dashboard-Zugriff. Prüfe seine Nachricht, bevor du entscheidest.
              </p>
            )
          }
          busy={busy !== null}
          onClose={() => setDecision(null)}
        >
          <div className="cloudtix-help-dialog-actions">
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => setDecision(null)}
              className="cloudtix-workspace-action is-secondary"
            >
              Abbrechen
            </button>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => void antworten()}
              className="cloudtix-workspace-action"
            >
              {busy !== null && <Loader2 size={14} className="animate-spin" />}
              {decision.type === "accepted"
                ? "Zugriff freigeben"
                : "Anfrage ablehnen"}
            </button>
          </div>
        </SupportDialog>
      )}
      {acceptedName && (
        <SupportDialog
          icon={CheckCircle2}
          title="Support-Zugriff freigegeben"
          description={
            <p>
              <strong>{acceptedName}</strong> kann deinen Server jetzt im
              Dashboard untersuchen. Öffne den aktiven Supportfall für
              Nachrichten oder um den Zugriff wieder zu beenden.
            </p>
          }
          busy={false}
          onClose={() => setAcceptedName("")}
        >
          <button
            type="button"
            onClick={() => {
              setAcceptedName("");
              setView("cases");
            }}
            className="cloudtix-workspace-action w-full mt-6"
          >
            Zu den Supportfällen
          </button>
        </SupportDialog>
      )}
      {closeId !== null && (
        <SupportDialog
          icon={Star}
          title="Supportfall abschließen"
          description={
            <p>
              Mit dem Schließen endet der Support-Zugriff. Bewerte die Hilfe von
              1 bis 10 und gib optional Feedback.
            </p>
          }
          busy={busy !== null}
          onClose={() => setCloseId(null)}
        >
          <fieldset disabled={busy !== null} className="cloudtix-help-rating">
            <legend>Deine Bewertung</legend>
            <div>
              {Array.from({ length: 10 }, (_, i) => i + 1).map((value) => (
                <button
                  key={value}
                  type="button"
                  aria-label={`${value} von 10`}
                  aria-pressed={rating === value}
                  data-selected={value <= rating}
                  onClick={() => setRating(value)}
                >
                  {value}
                </button>
              ))}
            </div>
            <p>
              {rating
                ? `${rating}/10 · ausgewählte Bewertung`
                : "Bitte eine Bewertung auswählen"}
            </p>
            <label htmlFor="support-rating-note">Feedback (optional)</label>
            <textarea
              id="support-rating-note"
              value={ratingNote}
              onChange={(e) => setRatingNote(e.target.value)}
              maxLength={1000}
              rows={3}
              placeholder="Was hat dir geholfen? Was können wir besser machen?"
              className="cloudtix-security-input"
            />
          </fieldset>
          <div className="cloudtix-help-dialog-actions">
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => setCloseId(null)}
              className="cloudtix-workspace-action is-secondary"
            >
              Abbrechen
            </button>
            <button
              type="button"
              onClick={() => void schliessen()}
              disabled={!rating || busy !== null}
              className="cloudtix-workspace-action"
            >
              {busy !== null && <Loader2 size={14} className="animate-spin" />}
              Bewerten & schließen
            </button>
          </div>
        </SupportDialog>
      )}
    </section>
  );
}
