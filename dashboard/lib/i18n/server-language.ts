import { cookies } from "next/headers";

export function websiteLocale(): string {
  return cookies().get("website-language")?.value === "en" ? "en-GB" : "de-DE";
}
