"use client";

/** Server-specific profile editor with an unsaved live preview. */

import { localizedConfirm } from "@/lib/i18n/browser-language";
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Eye,
  Info,
  ShieldCheck,
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
import { BRAND_LOGO } from "@/lib/brand";

const CARD = "cloudtix-workspace-card bg-[#131318] border border-slate-800 rounded-3xl p-4 sm:p-6";

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
    <div className="cloudtix-design-image-field">
      <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
        {titel}
      </label>
      <div className="mt-2 flex items-center gap-3">
        <div
          className={cn(
            "shrink-0 overflow-hidden border border-slate-800 cloudtix-workspace-card bg-[#0f0f13]",
            rund ? "h-20 w-20 rounded-full" : "h-20 w-32 rounded-xl"
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
            disabled={gesperrt}
            aria-label={titel}
            accept="image/png,image/jpeg,image/gif,image/webp"
            onChange={gewaehlt}
            className="hidden"
          />
          <button
            onClick={() => ref.current?.click()}
            disabled={gesperrt}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-800 cloudtix-workspace-card bg-[#0f0f13] px-3 py-2 text-xs text-slate-300 transition hover:bg-white/[0.04] disabled:opacity-40"
          >
            <Upload className="h-3 w-3" />
            Bild wählen
          </button>
          {wert && (
            <button
              onClick={() => onWechsel(null)}
              disabled={gesperrt}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-800 cloudtix-workspace-card bg-[#0f0f13] px-3 py-2 text-xs text-slate-400 transition hover:bg-white/[0.04] disabled:opacity-40"
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
  const [setztZurueck, setSetztZurueck] = useState(false);
  const [previewMode, setPreviewMode] = useState<"profile" | "message">("profile");

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

  // Wurde etwas geaendert?
  //
  // Der Vergleich laeuft gegen den ECHTEN Zustand aus Discord, nicht
  // gegen den zuletzt gespeicherten: aendert jemand den Nickname von
  // Hand in Discord, laufen beide auseinander, und der Knopf soll
  // das anzeigen, was man wirklich sieht.
  const urNickname = daten?.current?.nickname || "";
  const geaendert =
    nickname.trim() !== urNickname.trim() || avatar !== null || banner !== null;

  /** Alles zurueck auf den Stand, der gerade in Discord steht. */
  const zurueck = () => {
    setNickname(urNickname);
    setAvatar(null);
    setBanner(null);
  };

  /**
   * Zurueck auf das Profil aus dem Developer Portal.
   *
   * Loescht Server-Nickname, Server-Avatar und Server-Banner bei
   * Discord. Danach sieht der Bot hier wieder genauso aus wie
   * ueberall sonst.
   *
   * Bewusst mit Rueckfrage: der Knopf wirkt sofort auf Discord und
   * laesst sich nicht rueckgaengig machen -- die hochgeladenen Bilder
   * sind danach weg.
   */
  const aufStandard = async () => {
    const sicher = localizedConfirm(
      "Der Bot bekommt hier wieder sein normales Aussehen aus dem " +
        "Developer Portal.\n\nName, Profilbild und Banner für diesen " +
        "Server werden gelöscht. Das lässt sich nicht rückgängig machen."
    );
    if (!sicher) return;

    setSetztZurueck(true);
    try {
      uebernehmen(await api.designReset(guildId));
      toast.success("Zurückgesetzt — der Bot sieht hier wieder normal aus.");
    } catch (err: any) {
      toast.error(err?.message || "Zurücksetzen fehlgeschlagen.");
    } finally {
      setSetztZurueck(false);
    }
  };

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
  const gesperrt = !premium || !darf || beschaeftigt;
  const rechte = daten?.permissions || { ok: true, detail: "" };

  // Weicht das Server-Profil vom Developer Portal ab? Nur dann gibt
  // es überhaupt etwas zurückzusetzen. Die Antwort kommt vom Bot, der
  // den echten Zustand aus Discord liest.
  const weichtAb = Boolean(daten?.deviates?.abweichung);

  // Was die Vorschau zeigt: der Entwurf, sonst der echte Zustand.
  const zeigtName = nickname.trim() || jetzt.name || "CloudTIX";
  const zeigtAvatar = avatar ?? jetzt.avatar ?? null;
  const zeigtBanner = banner ?? jetzt.banner ?? null;

  if (!daten) return <section className="cloudtix-settings-card text-center"><ImageIcon className="mx-auto h-8 w-8 text-slate-500" /><h3 className="mt-4 text-lg">Profil nicht erreichbar</h3><p className="mt-2 text-sm text-slate-400">Das aktuelle Serverprofil konnte nicht geladen werden.</p><button onClick={() => void laden()} className="cloudtix-workspace-action mt-5">Erneut laden</button></section>;
  return <div className="cloudtix-settings-page">
    <header className="cloudtix-settings-heading"><div><p className="cloudtix-workspace-eyebrow">DEIN SERVER. DEIN STIL.</p><h1>Ein Profil für deine Community.</h1><p>Gestalte Name, Avatar und Banner von CloudTIX auf diesem Server.</p></div><button type="button" onClick={() => void speichern()} disabled={gesperrt || setztZurueck || !geaendert} className="cloudtix-workspace-action disabled:cursor-not-allowed disabled:opacity-40">{beschaeftigt ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}Speichern</button></header>
    {!premium && <section className="cloudtix-settings-premium-notice"><Crown size={20} /><div><h2>Mach CloudTIX zu einem Teil deines Servers.</h2><p>Ein eigenes Serverprofil ist mit Premium verfügbar. Die Vorschau kannst du hier ansehen.</p></div><Link href={`/dashboard/guild/${guildId}/premium`} className="cloudtix-workspace-action is-secondary">Premium öffnen<ArrowRight size={14} /></Link></section>}
    {premium && !darf && <div className="cloudtix-settings-running"><Lock size={17} /><p>Das Design darf hier nur der Server-Inhaber ändern.</p></div>}
    {premium && darf && !rechte.ok && <div role="alert" className="cloudtix-settings-warning"><strong>Der Bot kann das Profil hier nicht ändern.</strong><p>{rechte.detail}</p></div>}
    <div className="cloudtix-design-layout">
      <div className="space-y-5">
        <section className="cloudtix-settings-card"><div className="cloudtix-settings-card-title"><span><Sparkles size={18} /></span><div><h2>Identität</h2><p>So sehen Mitglieder den Bot auf deinem Server.</p></div></div><label htmlFor="cloudtix-profile-name" className="cloudtix-settings-field-label">Anzeigename</label><input id="cloudtix-profile-name" value={nickname} onChange={event => setNickname(event.target.value)} disabled={gesperrt || setztZurueck} maxLength={daten?.limits?.nickname ?? 32} placeholder={jetzt.name || "CloudTIX"} className="mt-2 w-full rounded-xl border border-white/15 bg-black/20 px-4 py-3 disabled:opacity-50" /><div className="mt-2 flex justify-between gap-3 text-[11px] text-slate-500"><p>Leer lassen für den normalen Bot-Namen.</p><span>{nickname.length}/{daten?.limits?.nickname ?? 32}</span></div></section>
        <section className="cloudtix-settings-card"><div className="cloudtix-settings-card-title"><span><ImageIcon size={18} /></span><div><h2>Bilder & Wiedererkennung</h2><p>Gib dem Profil den Look deiner Community.</p></div></div><div className="space-y-6"><BildFeld titel="Profilbild" hinweis="Quadratisch · PNG, JPEG, GIF oder WebP · bis 8 MB" wert={avatar} aktuell={jetzt.avatar || null} rund gesperrt={gesperrt || setztZurueck} onWechsel={setAvatar} /><BildFeld titel="Server-Banner" hinweis="Ein breites Bild hinter dem Profil. Die Anzeige hängt von Discord ab." wert={banner} aktuell={jetzt.banner || null} gesperrt={gesperrt || setztZurueck} onWechsel={setBanner} /></div></section>
        <section className="cloudtix-settings-card"><div className="cloudtix-design-draft-state"><span className={`cloudtix-settings-badge ${geaendert ? "has-changes" : ""}`}>{geaendert ? "Ungespeicherter Entwurf" : "Profil ist aktuell"}</span>{geaendert && <button type="button" onClick={zurueck} disabled={beschaeftigt || setztZurueck} className="text-xs text-slate-300 underline underline-offset-4">Entwurf verwerfen</button>}</div><p className="mt-3 text-xs leading-6 text-slate-500">Das Serverprofil gilt nur für {daten.guild_name || "diesen Server"}. Die Bio und das globale Profil werden über Discord verwaltet.</p>{weichtAb && <button type="button" onClick={() => void aufStandard()} disabled={gesperrt || setztZurueck} className="cloudtix-workspace-action is-secondary mt-4 w-full disabled:opacity-40">{setztZurueck ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}Standardprofil wiederherstellen</button>}</section>
      </div>
      <aside className="cloudtix-settings-card cloudtix-design-preview"><div className="cloudtix-settings-card-title"><span><Eye size={18} /></span><div><h2>Live-Vorschau</h2><p>Dein Entwurf. Noch nicht in Discord gespeichert.</p></div></div><nav className="cloudtix-settings-tabs" aria-label="Profilvorschau"><button type="button" aria-pressed={previewMode === "profile"} onClick={() => setPreviewMode("profile")}>Profil</button><button type="button" aria-pressed={previewMode === "message"} onClick={() => setPreviewMode("message")}>Nachricht</button></nav>
        {previewMode === "profile" ? <div className="cloudtix-design-profile" data-no-translate><div className="cloudtix-design-profile-banner">{zeigtBanner ? <img src={zeigtBanner} alt="Server-Banner in der Vorschau" /> : <div className="cloudtix-design-banner-placeholder"><ImageIcon size={26} /><span>Dein Server-Banner</span></div>}</div><div className="cloudtix-design-profile-content"><img src={zeigtAvatar || BRAND_LOGO} alt="Profilbild in der Vorschau" className="cloudtix-design-profile-avatar" /><span className="cloudtix-design-profile-online" title="Vorschau" /><div className="cloudtix-design-profile-name"><h3>{zeigtName}</h3><span>APP</span></div><p>{daten.guild_name || "Deine Community"}</p><div className="cloudtix-design-profile-about"><small>ÜBER MICH</small><p>Moderation, Tickets und Automationen für deine Community.</p><div><ShieldCheck size={14} /><span>CloudTIX · Serverprofil</span></div></div></div></div> : <div className="cloudtix-design-message" data-no-translate><img src={zeigtAvatar || BRAND_LOGO} alt="" /><div><div className="cloudtix-design-profile-name"><h3>{zeigtName}</h3><span>APP</span></div><small>Heute um 12:00 Uhr</small><p>Willkommen in unserer Community! Schön, dass du dabei bist.</p><div className="cloudtix-design-message-embed"><strong>Dein Server. Dein Stil.</strong><p>So erscheint CloudTIX mit deinem Profil auf diesem Server.</p></div></div></div>}
        <p className="cloudtix-design-preview-note"><Info size={14} />Die Darstellung ist eine Vorschau. Nach dem Speichern übernimmt Discord dein Serverprofil.</p>
      </aside>
    </div>
  </div>;
}
