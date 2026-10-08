import { createHmac } from "crypto";

export const LOUCKUP_COOKIE = "university-owner-louckup";
export const LOUCKUP_COOKIE_PATH = "/api/owner-louckup";

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
