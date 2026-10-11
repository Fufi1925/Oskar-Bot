"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { usePathname } from "next/navigation";
import { useSession } from "next-auth/react";
import { openLoginPanel } from "@/lib/login-panel";
import { Check, Loader2, Send, X } from "lucide-react";
import { api } from "@/lib/api";
import "./bug-report-button.css";

const DRAFT_KEY = "cloudtix-bug-report-draft";

function WormIcon() {
  return (
    <svg viewBox="0 0 40 40" fill="none" aria-hidden="true">
      <path
        d="M7 29c-3-1-3-5-1-7 2-3 6-3 8-1l3 3c2 2 5 1 6-2l2-8c1-4 6-6 9-3 4 3 2 7-1 9l-2 2c-2 1-3 3-3 5-1 7-7 9-12 5l-4-3c-1-1-3-1-5 0Z"
        fill="currentColor"
      />
      <path
        d="m13 23-3 4m9-1-1 5m7-10 5 2"
        stroke="#383838"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
      <circle cx="30" cy="13" r="1.2" fill="#171717" />
      <circle cx="34" cy="15" r="1.2" fill="#171717" />
    </svg>
  );
}

export function BugReportButton() {
  const pathname = usePathname();
  const { status } = useSession();
  const authenticationPage = pathname.startsWith("/auth/");
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [priority, setPriority] = useState("normal");
  const [page, setPage] = useState("/dashboard");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reportId, setReportId] = useState<number | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const titleInput = useRef<HTMLInputElement>(null);
  const sending = useRef(false);

  useEffect(() => setMounted(true), []);
  useEffect(() => {
    if (!mounted || status !== "authenticated" || authenticationPage) return;
    try {
      const saved = sessionStorage.getItem(DRAFT_KEY);
      if (!saved) return;
      const draft = JSON.parse(saved);
      if (
        typeof draft.title !== "string" ||
        typeof draft.body !== "string" ||
        typeof draft.page !== "string" ||
        !/^\/(?!\/)[A-Za-z0-9%_.~/-]*$/.test(draft.page) ||
        draft.title.length > 120 ||
        draft.body.length > 3500 ||
        draft.page.length > 300
      ) {
        sessionStorage.removeItem(DRAFT_KEY);
        return;
      }
      setTitle(draft.title);
      setBody(draft.body);
      setPage(draft.page);
      setPriority(
        ["low", "normal", "high", "critical"].includes(draft.priority)
          ? draft.priority
          : "normal",
      );
      setError("");
      setReportId(null);
      setOpen(true);
      sessionStorage.removeItem(DRAFT_KEY);
    } catch {
      // Storage may be unavailable. The form still works for signed-in users.
    }
  }, [mounted, status, authenticationPage]);
  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (!open) {
      if (element.open) element.close();
      return;
    }
    element.showModal();
    titleInput.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
      if (element.open) element.close();
    };
  }, [open, authenticationPage]);

  function openReport() {
    if (reportId !== null) {
      setTitle("");
      setBody("");
      setPriority("normal");
      setReportId(null);
    }
    setPage(pathname);
    setError("");
    setOpen(true);
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sending.current) return;
    if (title.trim().length < 5 || body.trim().length < 10) {
      setError(
        "Bitte gib einen Titel mit mindestens 5 Zeichen und eine Beschreibung mit mindestens 10 Zeichen ein.",
      );
      return;
    }
    if (status === "loading") return;
    if (status !== "authenticated") {
      try {
        sessionStorage.setItem(
          DRAFT_KEY,
          JSON.stringify({ title, body, page, priority }),
        );
      } catch {
        setError(
          "Dein Entwurf konnte nicht zwischengespeichert werden. Bitte melde dich zuerst an und öffne das Formular erneut.",
        );
        return;
      }
      openLoginPanel(window.location.href);
      return;
    }
    sending.current = true;
    setBusy(true);
    setError("");
    try {
      const result = await api.reportDashboardBug({
        title: title.trim(),
        body: body.trim(),
        page,
        priority,
      });
      if (!result.submitted || !result.id)
        throw new Error("Die Meldung konnte nicht gespeichert werden.");
      setReportId(result.id);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Die Meldung konnte nicht gesendet werden. Versuche es erneut.",
      );
    } finally {
      sending.current = false;
      setBusy(false);
    }
  }

  if (!mounted || authenticationPage || pathname.startsWith("/api/"))
    return null;
  return createPortal(
    <>
      <button
        type="button"
        className="cloudtix-bug-trigger"
        onClick={openReport}
        disabled={busy}
        aria-label="Bug melden"
        title="Bug melden"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="cloudtix-bug-dialog"
      >
        <WormIcon />
        <span className="cloudtix-bug-tooltip" aria-hidden="true">
          Bug melden
        </span>
      </button>
      <dialog
        ref={dialog}
        id="cloudtix-bug-dialog"
        className="cloudtix-bug-dialog"
        aria-labelledby="cloudtix-bug-title"
        aria-describedby="cloudtix-bug-description"
        onCancel={() => setOpen(false)}
        onClick={(event) => {
          const bounds = event.currentTarget.getBoundingClientRect();
          if (
            event.target === event.currentTarget &&
            (event.clientX < bounds.left ||
              event.clientX > bounds.right ||
              event.clientY < bounds.top ||
              event.clientY > bounds.bottom)
          )
            setOpen(false);
        }}
      >
        <header className="cloudtix-bug-header">
          <span className="cloudtix-bug-mark">
            <WormIcon />
          </span>
          <button
            type="button"
            className="cloudtix-bug-close"
            aria-label="Schließen"
            onClick={() => setOpen(false)}
          >
            <X size={20} />
          </button>
        </header>
        <p className="cloudtix-bug-eyebrow">CLOUDTIX / FEEDBACK</p>
        <h2 id="cloudtix-bug-title">
          {reportId ? "Danke für deine Hilfe." : "Einen Bug gefunden?"}
        </h2>
        <p id="cloudtix-bug-description">
          {reportId
            ? "Deine Meldung wurde gespeichert und kann vom Team bearbeitet werden."
            : "Sag uns, was passiert ist und wie wir den Fehler nachstellen können."}
        </p>
        {reportId ? (
          <div className="cloudtix-bug-success" role="status">
            <span>
              <Check size={20} /> Meldung #{reportId} eingegangen
            </span>
            <button
              type="button"
              className="cloudtix-bug-submit"
              onClick={() => setOpen(false)}
            >
              Fertig
            </button>
          </div>
        ) : (
          <form onSubmit={submit}>
            <fieldset disabled={busy} className="cloudtix-bug-fields">
              <label htmlFor="cloudtix-bug-summary">Kurzer Titel</label>
              <input
                ref={titleInput}
                id="cloudtix-bug-summary"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Zum Beispiel: Ticket-Einstellungen werden nicht gespeichert"
                required
                minLength={5}
                maxLength={120}
              />
              <label htmlFor="cloudtix-bug-body">Was funktioniert nicht?</label>
              <textarea
                id="cloudtix-bug-body"
                value={body}
                onChange={(event) => setBody(event.target.value)}
                rows={5}
                placeholder="Was hast du angeklickt? Was ist passiert und was hast du erwartet?"
                required
                minLength={10}
                maxLength={3500}
              />
              <div className="cloudtix-bug-counter">{body.length} / 3500</div>
              <label htmlFor="cloudtix-bug-priority">
                Wie sehr stört der Fehler?
              </label>
              <select
                id="cloudtix-bug-priority"
                value={priority}
                onChange={(event) => setPriority(event.target.value)}
              >
                <option value="low">Kleine Unstimmigkeit</option>
                <option value="normal">
                  Eine Funktion funktioniert nicht richtig
                </option>
                <option value="high">
                  Eine wichtige Funktion ist blockiert
                </option>
                <option value="critical">
                  Die Website oder das Dashboard ist nicht benutzbar
                </option>
              </select>
              <p className="cloudtix-bug-context">
                Betroffene Seite: <span>{page}</span>
              </p>
            </fieldset>
            {status === "unauthenticated" && (
              <p className="cloudtix-bug-context cloudtix-bug-login-note">
                Zum Absenden meldest du dich mit Discord an. Dein Entwurf bleibt
                erhalten.
              </p>
            )}
            {error && (
              <p role="alert" className="cloudtix-bug-error">
                {error}
              </p>
            )}
            <button
              type="submit"
              className="cloudtix-bug-submit"
              disabled={busy || status === "loading"}
            >
              {busy ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Send size={16} />
              )}
              {busy
                ? "Wird gesendet …"
                : status === "loading"
                  ? "Anmeldung wird geprüft …"
                  : status === "unauthenticated"
                    ? "Mit Discord anmelden und Bug melden"
                    : "Bug melden"}
            </button>
          </form>
        )}
      </dialog>
    </>,
    document.body,
  );
}
