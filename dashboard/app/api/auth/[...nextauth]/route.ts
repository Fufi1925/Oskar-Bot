import NextAuth from "next-auth";
import { NextRequest, NextResponse } from "next/server";
import { authOptions } from "@/lib/auth";
import { authErrorPath } from "@/lib/auth-errors";

const handler = NextAuth(authOptions);

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
      new URL(errorPath, process.env.NEXTAUTH_URL || request.url),
    );
  }
  return handler(request, context);
}

export { handler as POST };
