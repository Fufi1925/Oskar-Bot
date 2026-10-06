/** Shared by NextAuth and the Edge middleware that verifies its sessions. */
export function getAuthSecret(): string | undefined {
  return process.env.NEXTAUTH_SECRET || process.env.DASHBOARD_API_KEY;
}
