import { websiteOrigin } from "@/lib/website";
import NextAuth from "next-auth";
import { NextRequest, NextResponse } from "next/server";
import { authOptions, createAuthOptions } from "@/lib/auth";
import { authErrorPath } from "@/lib/auth-errors";
import { configuredOAuthScopes } from "@/lib/dashboard-oauth-policy";

async function handler(request: NextRequest, context: { params: { nextauth: string[] } }) {
  if (["signin", "callback"].includes(context.params.nextauth[0])) {
    try {
      const scopes = await configuredOAuthScopes();
      // Client-supplied authorization parameters must not override owner policy.
      request.nextUrl.searchParams.delete("scope");
      return NextAuth(createAuthOptions(scopes))(request, context);
    } catch {
      return NextResponse.redirect(new URL("/auth/error?error=OAuthSignin", websiteOrigin(new URL(request.url).origin)));
    }
  }
  return NextAuth(authOptions)(request, context);
}

export async function GET(
  request: NextRequest,
  context: { params: { nextauth: string[] } },
) {
  const errorPath = authErrorPath(
    context.params.nextauth[0],
    request.nextUrl.searchParams.get("error"),
  );
  if (errorPath) {
    return NextResponse.redirect(
      new URL(errorPath, websiteOrigin(new URL(request.url).origin)),
    );
  }
  return handler(request, context);
}

export { handler as POST };
