import type { Metadata } from "next";
import { cookies } from "next/headers";
import { readVerifyResult } from "@/lib/verification-oauth";
import { VerifyResult } from "@/components/verify-result";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Discord verification | CloudTIX",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default async function VerifyResultPage({ params, searchParams }: {
  params: Promise<{ guildId: string }>;
  searchParams: Promise<{ result?: string; lang?: string }>;
}) {
  const [{ guildId }, query] = await Promise.all([params, searchParams]);
  const outcome = query.result ? readVerifyResult(query.result) : null;
  const valid = !!outcome && outcome.guild_id === guildId;
  const language = query.lang === "en" || query.lang === "de" ? query.lang
    : valid && outcome.language ? outcome.language
    : cookies().get("website-language")?.value === "de" ? "de" : "en";
  return <VerifyResult guildId={guildId} language={language} outcome={valid ? outcome : null} />;
}
