/**
 * The operator's details, in one place.
 *
 * Every legal page needs the same handful of facts: who runs the
 * service, where they can be reached, what the thing is called. They
 * were read inline on each page with a different fallback each time,
 * which meant the imprint could say one thing and the terms another.
 *
 * Two rules this file exists to enforce:
 *
 * 1. **Nothing legally required is invented.** German law (§ 5 DDG)
 *    wants a real name and a postal address on anything offered to the
 *    public. Those can only come from the operator, so there is no
 *    fallback for them -- a missing address renders as a visible
 *    warning, not as a plausible-looking placeholder. A made-up
 *    imprint is worse than an obviously incomplete one.
 *
 * 2. **Cosmetic values may have fallbacks.** The brand name and the
 *    support invite are not legal requirements, so a sensible default
 *    is fine there.
 *
 * ── why these are read without the NEXT_PUBLIC_ prefix ──
 *
 * Next.js inlines NEXT_PUBLIC_* at **build time**. The Dockerfile only
 * passes three of them as build args, so NEXT_PUBLIC_IMPRINT_NAME and
 * friends were never present when the bundle was built -- setting them
 * in Railway did nothing at all, and the imprint stayed empty no matter
 * what the operator configured. Verified by building with them set and
 * watching the page still report every field as missing.
 *
 * All three legal pages are server components, so they can read the
 * plain process.env at request time instead. The NEXT_PUBLIC_ spelling
 * is still accepted as a fallback, because that is what is configured
 * today and breaking it would be a second bug.
 *
 * Nothing secret belongs in this file either way: an imprint is meant
 * to be read by everyone.
 */

/**
 * Read a setting, runtime value first.
 *
 * `IMPRINT_NAME` is read at request time and works when set in Railway.
 * `NEXT_PUBLIC_IMPRINT_NAME` only works if it was present during the
 * docker build, which is why the unprefixed name is preferred.
 */
function env(name: string): string | undefined {
  return process.env[name] ?? process.env[`NEXT_PUBLIC_${name}`];
}

/** Trim and treat whitespace-only as absent. */
function read(value: string | undefined): string {
  const text = (value || "").trim();
  // "." was what the address was actually set to at one point. A single
  // punctuation mark is not an address, and treating it as one produced
  // an imprint that looked filled in while being useless.
  if (!text || text === "." || text === "-") return "";
  return text;
}

export const BRAND = read(env("BRAND_NAME")) || "University Bot";

export const SUPPORT_INVITE =
  read(env("SUPPORT_INVITE")) || "https://discord.gg/MG3rYnUZJV";

/** § 5 DDG: the operator's name. No fallback on purpose. */
export const OPERATOR = read(env("IMPRINT_NAME"));

/** § 5 DDG: a postal address that could receive a letter. */
export const ADDRESS = read(env("IMPRINT_ADDRESS"));

/** § 5 DDG: an email address that is actually read. */
export const EMAIL = read(env("IMPRINT_EMAIL"));

/**
 * Optional extras. Only shown when set, because an empty "USt-IdNr.:"
 * line looks like something is broken.
 */
export const VAT_ID = read(env("IMPRINT_VAT_ID"));
export const REGISTER = read(env("IMPRINT_REGISTER"));

/** Where a data-protection request should go. Falls back to the imprint. */
export const PRIVACY_EMAIL =
  read(env("PRIVACY_EMAIL")) || EMAIL;

/**
 * Where the service runs. Named because a privacy policy has to say
 * who processes the data and where -- "somewhere in the cloud" is not
 * an answer under the GDPR.
 */
export const HOSTER = read(env("HOSTER")) || "Railway Corp.";
export const HOSTER_ADDRESS =
  read(env("HOSTER_ADDRESS")) ||
  "548 Market St PMB 68956, San Francisco, CA 94104, USA";

/** The address as a single line, for places that cannot use line breaks. */
export function addressOneLine(): string {
  return ADDRESS.replace(/\n/g, ", ");
}

/**
 * Everything § 5 DDG requires, and whether it is there.
 *
 * The pages use this to decide between showing the details and showing
 * a warning. Exported so a test can assert on it rather than parsing
 * rendered markup.
 */
export function imprintComplete(): boolean {
  return Boolean(OPERATOR && ADDRESS && EMAIL);
}

/** Which required fields are missing, for the warning banner. */
export function missingFields(): string[] {
  const missing: string[] = [];
  if (!OPERATOR) missing.push("Name des Betreibers");
  if (!ADDRESS) missing.push("Ladungsfähige Anschrift");
  if (!EMAIL) missing.push("E-Mail-Adresse");
  return missing;
}

/**
 * The date the legal texts were last changed.
 *
 * Written out rather than generated: "Stand: heute" on every page load
 * is worthless, and a build date changes when nothing about the text
 * did.
 */
export const LEGAL_UPDATED = "30. Juli 2026";
