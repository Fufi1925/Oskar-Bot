/**
 * Route protection.
 *
 * Everything under /dashboard requires a valid NextAuth session. Without this
 * middleware each page had to remember to call getServerSession() itself —
 * and 22 of 23 guild pages did not, which left them publicly reachable.
 *
 * Per-guild permission checks happen in the BFF proxy (app/api/bot/[...path])
 * and in the guild layout; this file only enforces "is signed in".
 */

import { withAuth } from "next-auth/middleware";

export default withAuth({
  pages: {
    signIn: "/",
    error: "/",
  },
});

export const config = {
  matcher: [
    "/dashboard/:path*",
    // The BFF proxy authorizes each request individually, but rejecting
    // anonymous traffic early keeps it cheap.
    "/api/bot/:path*",
  ],
};
