/**
 * The maintenance bypass.
 *
 * While WARTUNG=true this path is the only one that is not rewritten to
 * the notice. Enter the password and a cookie is set that lets this
 * browser through until maintenance ends.
 *
 * A server action rather than a client fetch: the password is compared
 * on the server, so it never reaches the browser bundle. Nothing links
 * here and the path is not guessable.
 */

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  BYPASS_COOKIE,
  BYPASS_MAX_AGE,
  bypassPassword,
  bypassToken,
  maintenanceOn,
} from "@/lib/maintenance";

export const dynamic = "force-dynamic";

async function unlock(formData: FormData) {
  "use server";

  const entered = String(formData.get("password") || "");
  if (entered !== bypassPassword()) {
    redirect("/526etrzeqwgoqfu32qzi?falsch=1");
  }

  cookies().set(BYPASS_COOKIE, bypassToken(), {
    httpOnly: true,
    sameSite: "lax",
    // Secure only over HTTPS; on a plain-HTTP preview the cookie would
    // otherwise be dropped and the unlock would silently do nothing.
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: BYPASS_MAX_AGE,
  });

  redirect("/");
}

export default function BypassPage({
  searchParams,
}: {
  searchParams?: { falsch?: string };
}) {
  const wrong = searchParams?.falsch === "1";
  const on = maintenanceOn();

  return (
    <html lang="de">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#071527",
          color: "#e2e8f0",
          fontFamily:
            'ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif',
          padding: "24px",
        }}
      >
        <main
          style={{
            maxWidth: "400px",
            width: "100%",
            background: "rgba(255,255,255,.02)",
            border: "1px solid rgba(255,255,255,.10)",
            borderRadius: "1.5rem",
            padding: "32px 30px",
          }}
        >
          <h1
            style={{
              margin: "0 0 6px",
              fontSize: "18px",
              fontWeight: 800,
              color: "#fff",
            }}
          >
            Wartungszugang
          </h1>
          <p
            style={{
              margin: "0 0 22px",
              fontSize: "13px",
              color: "#64748b",
              lineHeight: 1.6,
            }}
          >
            {on
              ? "Passwort eingeben, um die Seite trotz Wartung zu öffnen."
              : "Die Wartung ist gerade aus — hier gibt es nichts zu tun."}
          </p>

          <form action={unlock}>
            <input
              type="password"
              name="password"
              autoFocus
              autoComplete="off"
              placeholder="Passwort"
              style={{
                width: "100%",
                boxSizing: "border-box",
                background: "rgba(255,255,255,.03)",
                border: `1px solid ${wrong ? "rgba(248,113,113,.5)" : "rgba(255,255,255,.10)"}`,
                borderRadius: ".9rem",
                padding: "13px 16px",
                fontSize: "15px",
                color: "#e2e8f0",
                outline: "none",
              }}
            />

            {wrong && (
              <p
                style={{
                  margin: "10px 0 0",
                  fontSize: "13px",
                  color: "#fca5a5",
                }}
              >
                Falsches Passwort.
              </p>
            )}

            <button
              type="submit"
              style={{
                marginTop: "16px",
                width: "100%",
                background: "#3b82f6",
                border: "none",
                borderRadius: ".9rem",
                padding: "13px",
                fontSize: "14.5px",
                fontWeight: 700,
                color: "#fff",
                cursor: "pointer",
              }}
            >
              Freischalten
            </button>
          </form>
        </main>
      </body>
    </html>
  );
}
