import type { Language } from "./translations";
import { translateWebsiteText } from "./dom-translations";

export function validLanguage(value: unknown): Language | null {
  return value === "de" || value === "en" ? value : null;
}

export function currentWebsiteLanguage(): Language {
  if (typeof document === "undefined") return "de";
  return validLanguage(document.documentElement.lang) || "de";
}

export function localizedConfirm(message: string): boolean {
  return window.confirm(translateWebsiteText(message, currentWebsiteLanguage()));
}

export function localizedPrompt(message: string, initial?: string): string | null {
  return window.prompt(translateWebsiteText(message, currentWebsiteLanguage()), initial);
}

export function localizedAlert(message: string): void {
  window.alert(translateWebsiteText(message, currentWebsiteLanguage()));
}
