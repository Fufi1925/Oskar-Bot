/** NextAuth routes OAuth failures through its sign-in page, even when a
 * separate error page is configured. Keep those failures off the homepage. */
import { loginDestination } from "./auth-navigation";

export function authErrorPath(action: string | undefined, error: string | null, destination?: string | null, origin?: string): string | null {
  if (!error || (action !== "error" && action !== "signin")) return null;
  const next = destination ? `&next=${encodeURIComponent(loginDestination(destination, "/dashboard", origin))}` : "";
  return `/auth/error?error=${encodeURIComponent(error)}${next}`;
}
