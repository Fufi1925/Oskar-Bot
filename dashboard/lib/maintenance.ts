/**
 * Maintenance mode.
 *
 * `WARTUNG=true` puts the whole site behind a notice: every path, every
 * page, the API routes too. `false` or unset and nothing changes.
 *
 * The Discord bot is a separate process and is not touched by any of
 * this -- commands keep working while the website is down, which is
 * what the notice tells people.
 *
 * Read at request time, never at build time. A NEXT_PUBLIC_* name would
 * be baked into the JavaScript bundle when the image is built, so
 * flipping the Railway variable afterwards would change nothing.
 */

/** The cookie the bypass sets once the password has been accepted. */
export const BYPASS_COOKIE = "wartung_bypass";

/**
 * Secret path that offers the password prompt.
 *
 * Deliberately unguessable and not linked anywhere: while maintenance
 * is on, this is the only way in.
 */
export const BYPASS_PATH = "/526etrzeqwgoqfu32qzi";

/** How long a successful unlock lasts, in seconds. */
export const BYPASS_MAX_AGE = 60 * 60 * 8; // 8 hours

/** Is maintenance mode switched on right now? */
export function maintenanceOn(): boolean {
  const raw = (process.env.WARTUNG || "").trim().toLowerCase();
  // Accept the spellings someone might reasonably type into Railway.
  // Anything else -- including empty -- means off, because the safe
  // default for "did I set this right?" is a working site.
  return raw === "true" || raw === "1" || raw === "yes" || raw === "ja" || raw === "on";
}

/** The password for the bypass path. */
export function bypassPassword(): string {
  return process.env.WARTUNG_PASSWORT || "fufi67";
}

/**
 * The value stored in the bypass cookie.
 *
 * Not the password itself: a cookie is readable by anything with access
 * to the browser, and there is no reason to leave the password sitting
 * in one. This is a value derived from it, so the cookie stops working
 * the moment the password changes.
 */
export function bypassToken(): string {
  const secret = bypassPassword();
  let hash = 0;
  for (let i = 0; i < secret.length; i++) {
    hash = (hash << 5) - hash + secret.charCodeAt(i);
    hash |= 0;
  }
  return `ok-${Math.abs(hash).toString(36)}`;
}
