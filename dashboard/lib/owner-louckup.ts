import { websiteOrigin } from "./website";
import { createHmac } from "crypto";

export const LOUCKUP_COOKIE = "university-owner-louckup";
export const LOUCKUP_COOKIE_PATH = "/api/owner-louckup";

export function isLouckupOrigin(origin: string | null, requestOrigin: string): boolean {
  // Behind the bot proxy the request URL points at localhost. NEXTAUTH_URL
  // defines the trusted public origin; never trust caller-supplied proxy headers.
  try {
    const publicUrl = new URL(websiteOrigin(requestOrigin));
    if (!["https:", "http:"].includes(publicUrl.protocol) || publicUrl.username || publicUrl.password) return false;
    return origin === publicUrl.origin;
  } catch { return false; }
}

export function ownerBinding(userId: string, issuedAt: number, apiKey: string): string {
  return createHmac("sha256", apiKey).update(`owner-louckup:${userId}:${issuedAt}`).digest("hex");
}

export function allowedLouckupAction(parts: string[], method: string): boolean {
  if (parts.length === 1) {
    return method === "GET" ? parts[0] === "status" :
      method === "POST" && ["unlock", "lock"].includes(parts[0]);
  }
  return method === "GET" && parts.length === 2 && parts[0] === "users" && /^[0-9]{17,20}$/.test(parts[1]);
}
