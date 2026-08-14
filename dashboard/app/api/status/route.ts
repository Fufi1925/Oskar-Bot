import { NextRequest, NextResponse } from "next/server";

/**
 * Der Status-Wächter, für den Browser erreichbar gemacht.
 *
 * ── Warum es diese Route gibt ───────────────────────────────────────
 *
 * `STATUS_BOT_URL` zeigt auf einen Railway-internen Namen
 * (`…​.railway.internal`). Der ist absichtlich nur von innerhalb des
 * Projekts auflösbar — ein Browser kann ihn nicht erreichen, und die
 * Variable gehört auch nicht in die Seite geschrieben.
 *
 * Bisher lud die Status-Seite die Zahlen einmal beim Rendern auf dem
 * Server. Für eine Seite, die sich selbst aktualisieren soll, reicht
 * das nicht: der Browser braucht eine Adresse, die er selbst abfragen
 * kann. Das ist diese hier.
 *
 * ── Warum sie nichts prüft ──────────────────────────────────────────
 *
 * Kein Schlüssel, keine Anmeldung. Aus demselben Grund wie beim
 * Wächter selbst: eine Statusseite muss gerade dann funktionieren,
 * wenn nichts anderes mehr geht — auch für jemanden, der nicht auf dem
 * Discord-Server ist. Sie gibt nichts preis, was nicht ohnehin in
 * einem öffentlichen Kanal steht.
 *
 * ── Warum sie bei einem Ausfall 200 zurückgibt ──────────────────────
 *
 * Antwortet der Wächter nicht, kommt `{ ok: false }` mit HTTP 200
 * zurück, kein 502. Ein Fehlerstatus würde im Browser als
 * abgebrochene Anfrage landen, und die Seite müsste raten, ob der
 * Wächter aus ist oder das eigene Netz. So steht die Antwort da:
 * „nicht erreichbar" ist eine Auskunft, kein Fehler.
 */

const STATUS_BOT_URL = (process.env.STATUS_BOT_URL || "")
  .trim()
  .replace(/\/$/, "");

// Der Wächter ist der Dienst, der bei einem Ausfall antworten soll.
// Wartet die Seite zu lange auf ihn, ist sie selbst das Problem.
const TIMEOUT_MS = 5000;

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET(request: NextRequest) {
  if (!STATUS_BOT_URL) {
    return NextResponse.json(
      {
        ok: false,
        reason: "not_configured",
        detail: "STATUS_BOT_URL ist nicht gesetzt.",
      },
      { headers: { "Cache-Control": "no-store" } },
    );
  }

  // `history` holt den Verlauf, alles andere den aktuellen Zustand.
  const was = request.nextUrl.searchParams.get("was");
  const stunden = request.nextUrl.searchParams.get("stunden") || "24";

  const ziel =
    was === "history"
      ? `${STATUS_BOT_URL}/history.json?hours=${encodeURIComponent(stunden)}`
      : `${STATUS_BOT_URL}/status.json`;

  try {
    const antwort = await fetch(ziel, {
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });

    if (!antwort.ok) {
      return NextResponse.json(
        { ok: false, reason: "bad_status", status: antwort.status },
        { headers: { "Cache-Control": "no-store" } },
      );
    }

    const daten = await antwort.json();
    return NextResponse.json(
      { ok: true, data: daten },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (err: any) {
    // Zeitüberschreitung, DNS, Verbindung abgelehnt: für den Aufrufer
    // ist das alles dasselbe -- der Wächter antwortet nicht.
    return NextResponse.json(
      {
        ok: false,
        reason: "unreachable",
        detail: String(err?.name === "TimeoutError" ? "timeout" : err?.message || err),
      },
      { headers: { "Cache-Control": "no-store" } },
    );
  }
}
