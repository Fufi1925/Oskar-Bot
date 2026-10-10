/** Shared destinations for automatic Discord sign-in and the return trip. */
export const LOGIN_PATH = "/auth/login";

export function loginDestination(
  value: string | null | undefined,
  fallback = "/dashboard",
  origin?: string,
  depth = 0,
): string {
  if (!value || depth > 4 || /[\\\u0000-\u001f\u007f]/.test(value)) return fallback;
  if (value.startsWith("//")) return fallback;
  const base = origin || "https://cloudtix.up.railway.app";
  try {
    if (!value.startsWith("/") && !origin) return fallback;
    const url = new URL(value, base);
    if (url.origin !== new URL(base).origin || url.username || url.password) return fallback;
    const decodedPath = decodeURIComponent(url.pathname);
    if (decodedPath.startsWith("//") || /[\\\u0000-\u001f\u007f]/.test(decodedPath)) return fallback;
    if ([LOGIN_PATH, "/auth/success", "/api/auth/signin"].includes(url.pathname)) {
      return loginDestination(url.searchParams.get("next") || url.searchParams.get("callbackUrl"), fallback, base, depth + 1);
    }
    if (url.pathname.startsWith("/api/") || url.pathname === "/api" || url.pathname.startsWith("/auth/")) return fallback;
    return url.pathname + url.search + url.hash;
  } catch {
    return fallback;
  }
}

export function loginUrl(destination: string, origin?: string): string {
  return `${LOGIN_PATH}?next=${encodeURIComponent(loginDestination(destination, "/dashboard", origin))}`;
}

export function loginCallbackUrl(destination: string, origin?: string): string {
  return `/auth/success?next=${encodeURIComponent(loginDestination(destination, "/dashboard", origin))}`;
}
