import { websiteOrigin } from "@/lib/website";
import NextAuth from "next-auth";
import { NextRequest, NextResponse } from "next/server";
import { authOptions, createAuthOptions } from "@/lib/auth";
import { authErrorPath } from "@/lib/auth-errors";
import { configuredOAuthScopes } from "@/lib/dashboard-oauth-policy";

async function requestedDestination(request: NextRequest): Promise<string | null> {
  if (request.method === "POST") {
    try {
      const form = await request.clone().formData();
      const destination = form.get("callbackUrl");
      if (typeof destination === "string") return destination;
    } catch { /* Query/cookie fallback for requests without a form body. */ }
  }
  return request.nextUrl.searchParams.get("callbackUrl") ||
    request.cookies.get("__Secure-next-auth.callback-url")?.value ||
    request.cookies.get("next-auth.callback-url")?.value || null;
}

async function handler(request: NextRequest, context: { params: { nextauth: string[] } }) {
  if (["signin", "callback"].includes(context.params.nextauth[0])) {
    const destination = await requestedDestination(request);
    try {
      const scopes = await configuredOAuthScopes();
      // Client-supplied authorization parameters must not override owner policy.
      request.nextUrl.searchParams.delete("scope");
      return NextAuth(createAuthOptions(scopes))(request, context);
    } catch {
      const origin = websiteOrigin(new URL(request.url).origin);
      return NextResponse.redirect(new URL(authErrorPath("signin", "OAuthSignin", destination, origin)!, origin));
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
    await requestedDestination(request),
    websiteOrigin(new URL(request.url).origin),
  );
  if (errorPath) {
    return NextResponse.redirect(
      new URL(errorPath, websiteOrigin(new URL(request.url).origin)),
    );
  }
  return handler(request, context);
}

export { handler as POST };
