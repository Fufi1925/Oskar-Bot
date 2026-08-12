/**
 * The maintenance notice.
 *
 * Shown for every path while WARTUNG=true. The middleware rewrites to
 * this page rather than redirecting, so the address bar keeps whatever
 * the visitor typed and a refresh takes them back to where they were
 * once maintenance ends.
 *
 * It answers with 200, not 503: start.sh waits for `curl /` to succeed
 * before it starts the bot, and a 503 there would abort the whole
 * container -- taking the Discord bot down with it, which is the one
 * thing this notice promises is still running.
 */

export const dynamic = "force-dynamic";

const BRAND = process.env.NEXT_PUBLIC_BRAND_NAME || "University Bot";

export default function MaintenancePage() {
  return (
    <html lang="de">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0a0a0c",
          color: "#e2e8f0",
          fontFamily:
            'ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif',
          padding: "24px",
        }}
      >
        <main
          style={{
            maxWidth: "620px",
            width: "100%",
            background: "rgba(255,255,255,.02)",
            border: "1px solid rgba(255,255,255,.10)",
            borderRadius: "1.75rem",
            padding: "40px 36px",
            boxShadow: "0 24px 60px rgba(0,0,0,.45)",
          }}
        >
          <p
            style={{
              margin: "0 0 10px",
              fontSize: "11px",
              fontWeight: 900,
              letterSpacing: ".22em",
              textTransform: "uppercase",
              color: "#3b82f6",
            }}
          >
            {BRAND}
          </p>

          <h1
            style={{
              margin: "0 0 18px",
              fontSize: "27px",
              lineHeight: 1.25,
              fontWeight: 800,
              color: "#fff",
            }}
          >
            Website und Dashboard sind gerade in Wartung
          </h1>

          <p style={{ margin: "0 0 16px", fontSize: "15px", lineHeight: 1.7, color: "#cbd5e1" }}>
            Wir schließen gerade eine Sicherheitslücke. Voraussichtlich sind
            wir <strong style={{ color: "#fff" }}>heute um 0 Uhr</strong> wieder
            da.
          </p>

          <p style={{ margin: "0 0 22px", fontSize: "15px", lineHeight: 1.7, color: "#cbd5e1" }}>
            Unser Entwickler <strong style={{ color: "#fff" }}>Fufi</strong>{" "}
            kümmert sich darum.
          </p>

          {/* The one thing people actually want to know. */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "12px",
              background: "rgba(52,211,153,.08)",
              border: "1px solid rgba(52,211,153,.22)",
              borderRadius: "1rem",
              padding: "16px 18px",
            }}
          >
            <span
              style={{
                width: "9px",
                height: "9px",
                borderRadius: "50%",
                background: "#34d399",
                flex: "0 0 9px",
              }}
            />
            <p style={{ margin: 0, fontSize: "14.5px", lineHeight: 1.6, color: "#a7f3d0" }}>
              <strong style={{ color: "#6ee7b7" }}>Der Discord-Bot läuft normal weiter.</strong>{" "}
              Alle Befehle funktionieren wie gewohnt — nur Website und
              Dashboard sind vorübergehend nicht erreichbar.
            </p>
          </div>

          <p
            style={{
              margin: "24px 0 0",
              fontSize: "12.5px",
              color: "#63666f",
              lineHeight: 1.6,
            }}
          >
            Danke für deine Geduld.
          </p>
        </main>
      </body>
    </html>
  );
}
