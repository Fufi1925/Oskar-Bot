/** Public website origin shared by SEO, OAuth and origin checks. */
export const PUBLIC_WEBSITE_URL = "https://cloudtix.up.railway.app";

// These hosts are accepted only to migrate existing deployment settings.
const LEGACY_HOSTS = new Set([
  "universtiy-bot.up.railway.app",
  "university-bot.up.railway.app",
]);

function normalizedOrigin(value: string | undefined): string | null {
  let raw = (value || "").trim().replace(/^["']|["']$/g, "");
  if (!raw) return null;
  // A bare public hostname is a valid setting; arbitrary text is not.
  if (!raw.includes("://") && /^[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:\:\d+)?(?:\/.*)?$/i.test(raw)) {
    raw = `https://${raw}`;
  }
  try {
    const url = new URL(raw);
    if (!["http:", "https:"].includes(url.protocol) || !url.hostname ||
        url.hostname.startsWith(".") || url.username || url.password) return null;
    return LEGACY_HOSTS.has(url.hostname.toLowerCase()) ? PUBLIC_WEBSITE_URL : url.origin;
  } catch {
    return null;
  }
}

export function websiteOrigin(fallback = PUBLIC_WEBSITE_URL): string {
  const configured = [process.env.NEXTAUTH_URL, process.env.WEBSITE_URL,
    process.env.RAILWAY_PUBLIC_DOMAIN ? `https://${process.env.RAILWAY_PUBLIC_DOMAIN}` : undefined];
  for (const value of configured) {
    const origin = normalizedOrigin(value);
    if (origin) return origin;
  }
  // Broken environment settings must not crash page/auth module imports or
  // make a caller-supplied request host the trusted origin for sensitive actions.
  if (configured.some(value => value?.trim())) return PUBLIC_WEBSITE_URL;
  return normalizedOrigin(fallback) || PUBLIC_WEBSITE_URL;
}
