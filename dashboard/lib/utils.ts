/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║                                                                  ║
 * ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
 * ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
 * ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
 * ║                                                                  ║
 * ║           © 2026 University Bot Devs — All Rights Reserved               ║
 * ║                                                                  ║
 * ║   discord  ──  https://discord.gg/F3TedBAVZT                      ║
 * ║   youtube  ──  https://youtube.com/@University BotDevs                   ║
 * ║   github   ──  https://github.com/University Bot                        ║
 * ║                                                                  ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Steht diese ID in NEXT_PUBLIC_ADMIN_IDS?
 *
 * Nur für die Anzeige. Die Variable wird beim Build ins JavaScript
 * eingebacken und ist im Browser für jeden lesbar -- als Sperre taugt
 * sie nicht. Wer sie umgeht, landet trotzdem an der serverseitigen
 * Prüfung in app/dashboard/admin/page.tsx.
 *
 * Die Einträge werden getrimmt. Vorher wurde roh an Kommas getrennt,
 * also passte "123" nicht auf "111, 123" -- ein Leerzeichen hinter dem
 * Komma hat einen echten Admin ausgesperrt, und zwar lautlos.
 */
export function isAdmin(userId?: string | null) {
  if (!userId) return false;
  return (process.env.NEXT_PUBLIC_ADMIN_IDS || "")
    .split(",")
    .map((id) => id.trim())
    .filter(Boolean)
    .includes(String(userId).trim());
}

/**
 * Download a file from the API.
 *
 * Opening the URL in a tab (window.open) only saves the response when the
 * browser decides to honour Content-Disposition — for JSON it usually just
 * renders it instead. Fetching the bytes and driving a temporary <a download>
 * always produces a real file, and it surfaces API errors as a message rather
 * than a tab full of JSON.
 */
export async function downloadFile(url: string, fallbackName: string) {
  const response = await fetch(url, { cache: "no-store" });

  if (!response.ok) {
    let detail = `Download failed (${response.status})`;
    try {
      const data = await response.json();
      if (data?.detail) detail = String(data.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }

  // Prefer the filename the server picked.
  let filename = fallbackName;
  const disposition = response.headers.get("content-disposition") || "";
  const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^\";]+)"?/i);
  if (match?.[1]) filename = decodeURIComponent(match[1]);

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();

  // Give the browser a moment to start writing before revoking.
  setTimeout(() => URL.revokeObjectURL(objectUrl), 10_000);

  return filename;
}
