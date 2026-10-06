/** NextAuth routes OAuth failures through its sign-in page, even when a
 * separate error page is configured. Keep those failures off the homepage. */
export function authErrorPath(action: string | undefined, error: string | null): string | null {
  if (!error || (action !== "error" && action !== "signin")) return null;
  return `/auth/error?error=${encodeURIComponent(error)}`;
}
