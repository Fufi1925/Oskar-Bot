"use client";

/**
 * Design: wie der Bot auf DIESEM Server aussieht.
 *
 * Links die Einstellungen, rechts eine Vorschau, die aussieht wie
 * Discord. Was man tippt, steht sofort in der Vorschau — gespeichert
 * wird erst auf Knopfdruck.
 *
 * Ohne Premium
 * ------------
 * Die Vorschau bleibt sichtbar, die Felder sind gesperrt und darüber
 * liegt ein gelber Hinweis „Premium erforderlich“. Genau so in der
 * Skizze beschrieben. Man soll sehen, was es gäbe — sonst weiß
 * niemand, wofür er zahlen würde.
 *
 * Nur das Server-Profil
 * ---------------------
 * Nickname, Server-Avatar, Server-Banner. Der globale Bot-Name bleibt
 * unangetastet: Discord lässt davon nur zwei Änderungen pro Stunde zu,
 * und eine davon träfe alle Server gleichzeitig.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Crown,
  Image as ImageIcon,
  Loader2,
  Lock,
  RotateCcw,
  Save,
  Sparkles,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const CARD = "bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6";

/** Die gelbe Sperre aus der Skizze. */
function PremiumSperre() {
  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center rounded-3xl bg-[#0a0a0c]/75 backdrop-blur-[2px]">
      <div className="mx-4 max-w-sm rounded-2xl border-2 border-amber-400 bg-[#131318] p-5 text-center shadow-2xl">
        <div className="mx-auto mb-3 w-fit rounded-2xl bg-amber-400/15 p-3">
          <Crown className="h-6 w-6 text-amber-400" />
        </div>
        <div className="text-lg font-bold text-amber-400">
          Premium erforderlich
        </div>
        <p className="mt-2 text-sm leading-relaxed text-slate-400">
          Mit Premium gibst du dem Bot auf deinem Server einen eigenen Namen,
          ein eigenes Bild und ein eigenes Banner.
        </p>
        <Link
          href="/dashboard/premium"
          className="mt-4 inline-flex items-center gap-2 rounded-2xl bg-amber-400 px-4 py-2.5 text-sm font-bold text-black transition hover:brightness-110"
        >
          <Sparkles className="h-4 w-4" />
          Premium ansehen
        </Link>
      </div>
    </div>
  );
}

/** Ein Bildfeld mit Vorschau. */
function BildFeld({
  titel,
  hinweis,
  wert,
  aktuell,
  rund,
  gesperrt,
  onWechsel,
}: {
  titel: string;
  hinweis: string;
  wert: string | null;
  aktuell: string | null;
  rund?: boolean;
  gesperrt: boolean;
  onWechsel: (daten: string | null) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const zeigt = wert ?? aktuell;

  const gewaehlt = (e: React.ChangeEvent<HTMLInputElement>) => {
    const datei = e.target.files?.[0];
    if (!datei) return;
    if (datei.size > 8 * 1024 * 1024) {
      toast.error("Das Bild ist größer als 8 MB.");
      return;
    }
    const leser = new FileReader();
    leser.onload = () => onWechsel(String(leser.result));
    leser.onerror = () => toast.error("Das Bild ließ sich nicht lesen.");
    leser.readAsDataURL(datei);
  };

  return (
    <div>
      <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
        {titel}
      </label>
      <div className="mt-2 flex items-center gap-3">
        <div
          className={cn(
            "shrink-0 overflow-hidden border border-slate-800 bg-[#0f0f13]",
            rund ? "h-14 w-14 rounded-full" : "h-14 w-24 rounded-xl"
          )}
        >
          {zeigt ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={zeigt} alt="" className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full w-full items-center justify-center">
              <ImageIcon className="h-4 w-4 text-slate-700" />
            </div>
          )}
        </div>

        <div className="flex flex-1 flex-wrap gap-2">
          <input
            ref={ref}
            type="file"
            accept="image/png,image/jpeg,image/gif,image/webp"
            onChange={gewaehlt}
            className="hidden"
          />
          <button
            onClick={() => ref.current?.click()}
            disabled={gesperrt}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-800 bg-[#0f0f13] px-3 py-2 text-xs text-slate-300 transition hover:bg-white/[0.04] disabled:opacity-40"
          >
            <Upload className="h-3 w-3" />
            Bild wählen
          </button>
          {wert && (
            <button
              onClick={() => onWechsel(null)}
              disabled={gesperrt}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-800 bg-[#0f0f13] px-3 py-2 text-xs text-slate-400 transition hover:bg-white/[0.04] disabled:opacity-40"
            >
              <RotateCcw className="h-3 w-3" />
              Zurücksetzen
            </button>
          )}
        </div>
      </div>
      <p className="mt-1.5 text-xs text-slate-600">{hinweis}</p>
    </div>
  );
}

export function DesignPanel({ guildId }: { guildId: string }) {
  const [daten, setDaten] = useState<any>(null);
  const [laedt, setLaedt] = useState(true);
  const [beschaeftigt, setBeschaeftigt] = useState(false);

  const [nickname, setNickname] = useState("");
  const [avatar, setAvatar] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  const uebernehmen = useCallback((antwort: any) => {
    setDaten(antwort);
    setNickname(antwort.current?.nickname || "");
    setAvatar(null);
    setBanner(null);
  }, []);

  const laden = useCallback(async () => {
    try {
      uebernehmen(await api.design(guildId));
    } catch (err: any) {
      toast.error(err?.message || "Konnte das Design nicht laden.");
    } finally {
      setLaedt(false);
    }
  }, [guildId, uebernehmen]);

  useEffect(() => {
    laden();
  }, [laden]);

  const speichern = async () => {
    setBeschaeftigt(true);
    try {
      const nutzlast: any = { nickname };
      // Nur mitschicken, was sich geändert hat: ein `avatar: null`
      // würde sonst das vorhandene Bild löschen.
      if (avatar !== null) nutzlast.avatar = avatar;
      if (banner !== null) nutzlast.banner = banner;

      uebernehmen(await api.designSave(guildId, nutzlast));
      toast.success("Gespeichert — so sieht der Bot jetzt hier aus.");
    } catch (err: any) {
      toast.error(err?.message || "Speichern fehlgeschlagen.");
    } finally {
      setBeschaeftigt(false);
    }
  };

  if (laedt) {
    return (
      <div className={cn(CARD, "flex items-center gap-3 text-slate-400")}>
        <Loader2 className="h-4 w-4 animate-spin" />
        Wird geladen …
      </div>
    );
  }

  const jetzt = daten?.current || {};
  const darf = Boolean(daten?.may_edit);
  const premium = Boolean(daten?.premium);
  const gesperrt = !darf || beschaeftigt;
  const rechte = daten?.permissions || { ok: true, detail: "" };

  // Was die Vorschau zeigt: der Entwurf, sonst der echte Zustand.
  const zeigtName = nickname.trim() || jetzt.name || "University Bot";
  const zeigtAvatar = avatar ?? jetzt.avatar ?? null;
  const zeigtBanner = banner ?? jetzt.banner ?? null;

  return (
    <div className="space-y-4">
      {/* ── Fehlende Rechte zuerst ────────────────────────────────── */}
      {premium && darf && !rechte.ok && (
        <div className="flex gap-3 rounded-3xl border border-red-500/30 bg-red-500/5 p-4">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-400" />
          <div>
            <div className="font-semibold text-white">
              Der Bot kann seinen Namen hier nicht ändern
            </div>
            <p className="mt-1 text-sm text-red-200/80">{rechte.detail}</p>
          </div>
        </div>
      )}

      {/* Premium ja, aber nicht Inhaber. Bewusst knapp: dass es eine
          Freischaltliste gibt, steht hier nicht. */}
      {premium && !darf && (
        <div className="flex gap-3 rounded-3xl border border-slate-800 bg-[#0f0f13] p-4">
          <Lock className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
          <p className="text-sm text-slate-400">
            Das Design darf hier nur der Server-Inhaber ändern.
          </p>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* ── Links: die Einstellungen ───────────────────────────── */}
        <div className="relative">
          {!premium && <PremiumSperre />}

          <div className={cn(CARD, "space-y-5", !premium && "select-none")}>
            <div>
              <h3 className="font-bold text-white">Aussehen auf diesem Server</h3>
              <p className="mt-1 text-sm text-slate-400">
                Gilt nur hier. Auf allen anderen Servern bleibt der Bot, wie er
                ist.
              </p>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
                Name
              </label>
              <input
                value={nickname}
                onChange={(e) => setNickname(e.target.value)}
                disabled={gesperrt}
                maxLength={daten?.limits?.nickname ?? 32}
                placeholder={jetzt.name || "University Bot"}
                className="mt-2 w-full rounded-2xl border border-slate-800 bg-[#0f0f13] px-4 py-3 text-sm text-white outline-none focus:border-primary/50 disabled:opacity-50"
              />
              <p className="mt-1.5 text-xs text-slate-600">
                Leer lassen = der normale Bot-Name. Höchstens{" "}
                {daten?.limits?.nickname ?? 32} Zeichen.
              </p>
            </div>

            <BildFeld
              titel="Profilbild"
              hinweis="Quadratisch, PNG/JPEG/GIF/WebP, bis 8 MB."
              wert={avatar}
              aktuell={jetzt.avatar || null}
              rund
              gesperrt={gesperrt}
              onWechsel={setAvatar}
            />

            <BildFeld
              titel="Banner"
              hinweis="Breites Bild hinter dem Profil. Nicht jeder Server kann es anzeigen."
              wert={banner}
              aktuell={jetzt.banner || null}
              gesperrt={gesperrt}
              onWechsel={setBanner}
            />

            <button
              onClick={speichern}
              disabled={gesperrt}
              className="inline-flex items-center gap-2 rounded-2xl bg-primary px-5 py-3 text-sm font-semibold text-white transition hover:brightness-110 disabled:opacity-40"
            >
              {beschaeftigt ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Speichern
            </button>
          </div>
        </div>

        {/* ── Rechts: die Vorschau ───────────────────────────────── */}
        <div className={CARD}>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-bold text-white">Live-Vorschau</h3>
            <span className="rounded-lg bg-[#0f0f13] px-2 py-0.5 text-xs text-slate-500">
              so sieht er hier aus
            </span>
          </div>

          {/* Ein Discord-Profil, nachgebaut. */}
          <div className="overflow-hidden rounded-2xl border border-[#1e1f22] bg-[#232428]">
            <div className="h-20 w-full bg-[#5865f2]">
              {zeigtBanner && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={zeigtBanner}
                  alt=""
                  className="h-full w-full object-cover"
                />
              )}
            </div>

            <div className="px-4 pb-4">
              <div className="-mt-10 mb-2 h-20 w-20 overflow-hidden rounded-full border-[6px] border-[#232428] bg-[#1e1f22]">
                {zeigtAvatar ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={zeigtAvatar}
                    alt=""
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="flex h-full w-full items-center justify-center text-slate-700">
                    <ImageIcon className="h-5 w-5" />
                  </div>
                )}
              </div>

              <div className="rounded-xl bg-[#111214] p-3">
                <div className="flex items-center gap-1.5">
                  <span className="text-lg font-bold text-white">
                    {zeigtName}
                  </span>
                  <span className="rounded bg-[#5865f2] px-1 text-[10px] font-bold uppercase text-white">
                    App
                  </span>
                </div>
                {daten?.guild_name && (
                  <div className="mt-1 text-xs text-[#949ba4]">
                    auf {daten.guild_name}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Wie eine Nachricht von ihm aussieht. */}
          <div className="mt-3 rounded-2xl border border-[#1e1f22] bg-[#313338] p-3">
            <div className="flex gap-3">
              <div className="h-9 w-9 shrink-0 overflow-hidden rounded-full bg-[#1e1f22]">
                {zeigtAvatar && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={zeigtAvatar}
                    alt=""
                    className="h-full w-full object-cover"
                  />
                )}
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm font-medium text-white">
                    {zeigtName}
                  </span>
                  <span className="rounded bg-[#5865f2] px-1 text-[10px] font-bold uppercase text-white">
                    App
                  </span>
                  <span className="text-[11px] text-[#949ba4]">heute</span>
                </div>
                <div className="text-sm text-[#dbdee1]">
                  So sieht eine Nachricht von mir hier aus.
                </div>
              </div>
            </div>
          </div>

          <p className="mt-3 text-xs text-slate-600">
            Die Vorschau zeigt deinen Entwurf. Erst nach dem Speichern ändert
            sich etwas in Discord.
          </p>
        </div>
      </div>
    </div>
  );
}
