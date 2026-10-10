/** Public website origin shared by SEO, OAuth and origin checks. */
export const PUBLIC_WEBSITE_URL = "https://cloudtix.up.railway.app";

// These hosts are accepted only to migrate existing deployment settings.
const LEGACY_HOSTS = new Set([
  "universtiy-bot.up.railway.app",
  "university-bot.up.railway.app",
]);

export function websiteOrigin(fallback = PUBLIC_WEBSITE_URL): string {
  const raw = process.env.NEXTAUTH_URL || process.env.WEBSITE_URL ||
    (process.env.RAILWAY_PUBLIC_DOMAIN ? `https://${process.env.RAILWAY_PUBLIC_DOMAIN}` : fallback);
  const url = new URL(raw.trim().replace(/^["']|["']$/g, ""));
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
    throw new Error("Invalid public website origin");
  }
  return LEGACY_HOSTS.has(url.hostname.toLowerCase()) ? PUBLIC_WEBSITE_URL : url.origin;
}
