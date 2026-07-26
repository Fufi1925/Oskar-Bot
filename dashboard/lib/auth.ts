import DiscordProvider from "next-auth/providers/discord";
import { AuthOptions } from "next-auth";

const DISCORD_CLIENT_ID = process.env.DISCORD_CLIENT_ID || "";
const DISCORD_CLIENT_SECRET = process.env.DISCORD_CLIENT_SECRET || "";

export const authOptions: AuthOptions = {
  providers: [
    DiscordProvider({
      clientId: DISCORD_CLIENT_ID,
      clientSecret: DISCORD_CLIENT_SECRET,
      authorization: { 
        params: { 
          scope: "identify guilds",
        } 
      },
    }),
  ],
  callbacks: {
    /**
     * Records every sign-in with the bot so the admin panel can show who has
     * been in the dashboard — and refuses the sign-in outright when that user
     * is on the dashboard ban list.
     */
    async signIn({ user, profile }) {
      const userId = (profile as any)?.id || user?.id;
      if (!userId) return true;

      try {
        const { recordLogin } = await import("@/lib/guild-auth");
        const avatar = user?.image || "";
        const username =
          (profile as any)?.username ||
          (profile as any)?.global_name ||
          user?.name ||
          "";

        const banned = await recordLogin(String(userId), String(username), String(avatar));
        if (banned) {
          // NextAuth turns this into ?error=AccessDenied on the sign-in page.
          return false;
        }
      } catch {
        // Never block a login because the bookkeeping call failed.
      }
      return true;
    },

    async jwt({ token, account }) {
      if (account) {
        token.accessToken = account.access_token;
        token.refreshToken = account.refresh_token;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        // @ts-ignore
        session.user.id = token.sub;
        // @ts-ignore
        session.accessToken = token.accessToken;
      }
      return session;
    },
    async redirect({ url, baseUrl }) {
      if (url.startsWith("/")) {
        return `${baseUrl}${url}`;
      }
      if (new URL(url).origin === baseUrl) {
        return url;
      }
      return baseUrl;
    },
  },
  session: {
    strategy: "jwt",
    maxAge: 30 * 24 * 60 * 60,
  },
  secret: process.env.NEXTAUTH_SECRET || process.env.DASHBOARD_API_KEY,
  pages: {
    signIn: "/",
    error: "/",
  },
  debug: true,
};
