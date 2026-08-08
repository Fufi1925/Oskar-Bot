"use client";

/**
 * Hochladen: den eigenen Server als Vorlage teilen.
 *
 * Drei Schritte, bewusst nacheinander:
 *
 *   1. **Scannen** — der Bot liest Kanäle, Rollen, Rechte und die
 *      Dashboard-Einstellungen. Es wird noch nichts gespeichert.
 *   2. **Auswählen** — was soll wirklich mit? Jede Funktion einzeln
 *      abwählbar.
 *   3. **Veröffentlichen** — Name, Beschreibung, offen oder mit
 *      Zugangscode.
 *
 * ── Warum der Scan getrennt ist ─────────────────────────────────────
 *
 * Man soll sehen, was mitginge, bevor man es öffentlich macht. Ein
 * Knopf, der in einem Zug scannt und veröffentlicht, wäre schneller —
 * aber niemand hätte je geprüft, was in der Vorlage steht.
 *
 * ── Was der Bot dabei entfernt ──────────────────────────────────────
 *
 * IDs werden zu Platzhaltern, Webhook-Adressen, Tokens und
 * Einladungen fallen ganz heraus. Das passiert auf der Serverseite,
 * nicht hier: was gar nicht erst gespeichert wird, kann auch nicht
 * versehentlich ausgeliefert werden.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle, Check, Copy, Hash, Loader2, Lock, ScanLine, Shield,
  Trash2, Upload, Users, Volume2,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { InlineToggle } from "@/components/dashboard/form-elements";

const CARD =
  "bg-[#10233f] border border-slate-800 rounded-3xl p-4 sm:p-6 border-glow-card";
const INPUT =
  "w-full bg-[#0a1628] border border-slate-800 rounded-xl px-4 py-3 text-sm " +
  "text-white placeholder:text-slate-600 focus:outline-none " +
  "focus:border-primary/50 transition-colors";

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <span className="text-xs font-black uppercase tracking-widest text-slate-500">
        {label}
      </span>
      {children}
      {hint && (
        <p className="text-[11px] text-slate-600 leading-relaxed">{hint}</p>
      )}
    </div>
  );
}

export function TemplateUploadPanel({ guildId }: { guildId: string }) {
  const [scan, setScan] = useState<any>(null);
  const [scanning, setScanning] = useState(false);
  const [busy, setBusy] = useState("");
  const [own, setOwn] = useState<any[]>([]);

  // Was mit soll
  const [include, setInclude] = useState({
    roles: true,
    channels: true,
    permissions: true,
    features: true,
  });
  const [featureKeys, setFeatureKeys] = useState<Record<string, boolean>>({});

  // Veröffentlichen
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState<"public" | "key">("public");
  const [issuedKey, setIssuedKey] = useState("");

  const loadOwn = useCallback(async () => {
    try {
      const answer = await api.templateList(guildId);
      setOwn(answer?.own || []);
    } catch {
      // Die eigene Liste ist Beiwerk — ein Fehlschlag hier darf den
      // Upload nicht blockieren.
    }
  }, [guildId]);

  useEffect(() => {
    loadOwn();
  }, [loadOwn]);

  const runScan = async () => {
    setScanning(true);
    try {
      const answer = await api.templateScan(guildId);
      setScan(answer);
      // Alle gefundenen Funktionen zunächst an.
      const keys: Record<string, boolean> = {};
      for (const entry of answer?.preview?.features || []) {
        keys[entry.key] = true;
      }
      setFeatureKeys(keys);
      if (!name) setName(answer?.preview?.name || "");
    } catch (error: any) {
      toast.error(error?.message || "Der Server ließ sich nicht einlesen.");
    } finally {
      setScanning(false);
    }
  };

  const publish = async () => {
    if (!name.trim()) {
      toast.error("Die Vorlage braucht einen Namen.");
      return;
    }
    setBusy("upload");
    try {
      const answer = await api.templateUpload(guildId, {
        name: name.trim(),
        description: description.trim(),
        visibility,
        include,
        feature_keys: featureKeys,
      });
      if (answer?.key) {
        setIssuedKey(answer.key);
      } else {
        toast.success("Vorlage veröffentlicht.");
      }
      setName("");
      setDescription("");
      setScan(null);
      await loadOwn();
    } catch (error: any) {
      toast.error(error?.message || "Das Hochladen schlug fehl.");
    } finally {
      setBusy("");
    }
  };

  const preview = scan?.preview;
  const counts = scan?.counts || {};

  return (
    <div className="space-y-5">
      {/* Der Zugangscode — genau einmal sichtbar */}
      {issuedKey && (
        <div className="rounded-2xl bg-emerald-500/[0.07] border border-emerald-500/30 p-5 space-y-3">
          <div className="flex items-center gap-2.5">
            <Lock className="h-4 w-4 text-emerald-400" />
            <p className="text-[13px] font-bold text-emerald-200">
              Vorlage veröffentlicht — hier ist der Zugangscode
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <code className="px-4 py-2.5 rounded-xl bg-[#0a1628] border border-emerald-500/25 text-lg font-black tracking-[0.3em] text-emerald-300">
              {issuedKey}
            </code>
            <button
              onClick={() => {
                navigator.clipboard?.writeText(issuedKey);
                toast.success("Kopiert.");
              }}
              className="flex items-center gap-2 px-3.5 py-2.5 rounded-xl bg-white/[0.04] border border-white/10 text-xs font-bold text-slate-300 hover:text-white transition-all"
            >
              <Copy className="h-3.5 w-3.5" />
              Kopieren
            </button>
          </div>
          <p className="text-[12px] text-emerald-200/70 leading-relaxed">
            Bitte jetzt notieren. Der Code wird nur als Prüfsumme gespeichert
            und lässt sich später nicht mehr anzeigen — wer ihn verliert, muss
            die Vorlage neu hochladen.
          </p>
          <button
            onClick={() => setIssuedKey("")}
            className="text-[11px] font-bold uppercase tracking-widest text-emerald-400/70 hover:text-emerald-300"
          >
            Verstanden
          </button>
        </div>
      )}

      {/* ── 1. Scannen ───────────────────────────────────── */}
      <div className={cn(CARD, "space-y-5")}>
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-primary/10 grid place-items-center shrink-0">
            <ScanLine className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h3 className="font-bold text-white">Server einlesen</h3>
            <p className="text-[12px] text-slate-500 mt-0.5">
              Kanäle, Rollen, Rechte und Einstellungen — es wird noch nichts
              gespeichert.
            </p>
          </div>
        </div>

        <button
          disabled={scanning}
          onClick={runScan}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-primary/15 border border-primary/40 text-primary text-xs font-black uppercase tracking-widest hover:bg-primary/20 disabled:opacity-40 transition-all"
        >
          {scanning ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <ScanLine className="h-3.5 w-3.5" />
          )}
          {scan ? "Erneut einlesen" : "Server einlesen"}
        </button>

        {preview && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: "Kategorien", value: counts.categories, icon: Hash },
                { label: "Kanäle", value: counts.channels, icon: Volume2 },
                { label: "Rollen", value: counts.roles, icon: Users },
                { label: "Funktionen", value: counts.features, icon: Shield },
              ].map((entry) => (
                <div
                  key={entry.label}
                  className="rounded-2xl bg-[#0a1628] border border-slate-800 px-4 py-3"
                >
                  <p className="text-[9px] font-black uppercase tracking-widest text-slate-600">
                    {entry.label}
                  </p>
                  <p className="text-lg font-black text-white mt-1">
                    {entry.value ?? 0}
                  </p>
                </div>
              ))}
            </div>

            <div className="rounded-2xl bg-[#0a1628] border border-slate-800 p-4 space-y-3 max-h-72 overflow-y-auto">
              {preview.roles?.length > 0 && (
                <div>
                  <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 mb-2">
                    Rollen
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {preview.roles.map((role: any) => (
                      <span
                        key={role.name}
                        className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/[0.04] border border-white/10 text-[11px] text-slate-300"
                      >
                        <span
                          className="h-2 w-2 rounded-full shrink-0"
                          style={{ background: role.colour || "#99aab5" }}
                        />
                        {role.name}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {preview.channels?.length > 0 && (
                <div>
                  <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 mb-2 mt-3">
                    Kanäle
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {preview.channels.slice(0, 60).map((channel: any) => (
                      <span
                        key={`${channel.category}-${channel.name}`}
                        className="px-2.5 py-1 rounded-lg bg-white/[0.04] border border-white/10 text-[11px] text-slate-400"
                      >
                        {channel.kind === "voice" ? "🔊" : "#"} {channel.name}
                      </span>
                    ))}
                    {preview.channels.length > 60 && (
                      <span className="px-2.5 py-1 text-[11px] text-slate-600">
                        … und {preview.channels.length - 60} weitere
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* ── 2. Auswählen ─────────────────────────────────── */}
      {preview && (
        <div className={cn(CARD, "space-y-4")}>
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-primary/10 grid place-items-center shrink-0">
              <Check className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h3 className="font-bold text-white">Was soll mit?</h3>
              <p className="text-[12px] text-slate-500 mt-0.5">
                Alles Abgewählte landet gar nicht erst in der Vorlage.
              </p>
            </div>
          </div>

          <InlineToggle
            checked={include.roles}
            onCheckedChange={(v: boolean) =>
              setInclude((old) => ({ ...old, roles: v }))
            }
            label="Rollen"
            hint="Name, Farbe, Rechte und ob sie getrennt angezeigt werden."
          />
          <InlineToggle
            checked={include.channels}
            onCheckedChange={(v: boolean) =>
              setInclude((old) => ({ ...old, channels: v }))
            }
            label="Kanäle und Kategorien"
            hint="Mit Thema, Reihenfolge und Slowmode."
          />
          <InlineToggle
            checked={include.permissions}
            onCheckedChange={(v: boolean) =>
              setInclude((old) => ({ ...old, permissions: v }))
            }
            label="Kanalrechte"
            hint="Welche Rolle wo was darf. Ohne das entstehen Kanäle mit den Serverstandards."
          />
          <InlineToggle
            checked={include.features}
            onCheckedChange={(v: boolean) =>
              setInclude((old) => ({ ...old, features: v }))
            }
            label="Dashboard-Einstellungen"
            hint="Verifizierung, Leveling, Automod und so weiter."
          />

          {include.features && preview.features?.length > 0 && (
            <div className="rounded-2xl bg-[#0a1628] border border-slate-800 p-4 space-y-2">
              <p className="text-[10px] font-black uppercase tracking-widest text-slate-600 mb-1">
                Dashboard erweitert — einzeln abwählbar
              </p>
              {preview.features.map((entry: any) => (
                <label
                  key={entry.key}
                  className="flex items-center gap-3 py-1.5 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={featureKeys[entry.key] ?? true}
                    onChange={(event) =>
                      setFeatureKeys((old) => ({
                        ...old,
                        [entry.key]: event.target.checked,
                      }))
                    }
                    className="accent-primary h-4 w-4"
                  />
                  <span className="text-[13px] text-slate-200 flex-1">
                    {entry.label}
                  </span>
                  <span className="text-[11px] text-slate-600">
                    {entry.entries} Eintrag/Einträge
                  </span>
                </label>
              ))}
            </div>
          )}

          <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/20 p-3.5 flex gap-2.5">
            <Shield className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
            <p className="text-[12px] text-amber-200/80 leading-relaxed">
              Kanal- und Rollen-IDs werden durch Platzhalter ersetzt.
              Webhook-Adressen, Tokens und Einladungslinks fallen ganz heraus —
              sie wären sonst für jeden sichtbar, der die Vorlage ansieht.
            </p>
          </div>
        </div>
      )}

      {/* ── 3. Veröffentlichen ───────────────────────────── */}
      {preview && (
        <div className={cn(CARD, "space-y-5")}>
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-primary/10 grid place-items-center shrink-0">
              <Upload className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h3 className="font-bold text-white">Veröffentlichen</h3>
              <p className="text-[12px] text-slate-500 mt-0.5">
                {scan?.already ?? 0} von {scan?.limits?.max_per_guild ?? 10}{" "}
                Vorlagen belegt.
              </p>
            </div>
          </div>

          <Field label="Name">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={scan?.limits?.max_name ?? 80}
              placeholder="z. B. Gaming-Community"
              className={INPUT}
            />
          </Field>

          <Field
            label="Beschreibung"
            hint="Wofür ist die Vorlage gedacht? Hilft anderen bei der Suche."
          >
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
              maxLength={scan?.limits?.max_description ?? 500}
              placeholder="Kurz erklärt, was drin ist …"
              className={cn(INPUT, "resize-y")}
            />
          </Field>

          <Field label="Sichtbarkeit">
            <div className="grid sm:grid-cols-2 gap-2">
              <button
                onClick={() => setVisibility("public")}
                className={cn(
                  "rounded-xl border px-4 py-3 text-left transition-all",
                  visibility === "public"
                    ? "bg-primary/10 border-primary/40"
                    : "bg-[#0a1628] border-slate-800 hover:border-slate-700"
                )}
              >
                <p className="text-[13px] font-bold text-white">Offen</p>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Jeder sieht die Vorschau und kann sie anwenden.
                </p>
              </button>
              <button
                onClick={() => setVisibility("key")}
                className={cn(
                  "rounded-xl border px-4 py-3 text-left transition-all",
                  visibility === "key"
                    ? "bg-primary/10 border-primary/40"
                    : "bg-[#0a1628] border-slate-800 hover:border-slate-700"
                )}
              >
                <p className="text-[13px] font-bold text-white">
                  Mit Zugangscode
                </p>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Nur Name und Beschreibung sind öffentlich. Vorschau erst mit
                  Code.
                </p>
              </button>
            </div>
          </Field>

          <button
            disabled={!name.trim() || busy === "upload"}
            onClick={publish}
            className="flex items-center gap-2 px-5 py-3 rounded-xl bg-primary/15 border border-primary/40 text-primary text-xs font-black uppercase tracking-widest hover:bg-primary/20 disabled:opacity-40 transition-all"
          >
            {busy === "upload" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Upload className="h-3.5 w-3.5" />
            )}
            Veröffentlichen
          </button>
        </div>
      )}

      {/* ── Eigene Vorlagen ──────────────────────────────── */}
      {own.length > 0 && (
        <div className={cn(CARD, "space-y-4")}>
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-primary/10 grid place-items-center shrink-0">
              <Users className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h3 className="font-bold text-white">Eigene Vorlagen</h3>
              <p className="text-[12px] text-slate-500 mt-0.5">
                Von diesem Server hochgeladen.
              </p>
            </div>
          </div>

          <div className="space-y-2">
            {own.map((entry: any) => (
              <div
                key={entry.id}
                className="flex items-center gap-3 rounded-2xl bg-[#0a1628] border border-slate-800 p-4 flex-wrap"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="text-[13px] font-bold text-white truncate">
                      {entry.name}
                    </p>
                    {entry.visibility === "key" && (
                      <Lock className="h-3 w-3 text-amber-400 shrink-0" />
                    )}
                  </div>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    {entry.summary.channels} Kanäle · {entry.summary.roles}{" "}
                    Rollen · {entry.uses}× verwendet
                  </p>
                </div>
                <button
                  onClick={async () => {
                    setBusy(`del${entry.id}`);
                    try {
                      await api.templateDelete(guildId, entry.id);
                      await loadOwn();
                      toast.success("Gelöscht.");
                    } catch (error: any) {
                      toast.error(error?.message || "Das ging nicht.");
                    } finally {
                      setBusy("");
                    }
                  }}
                  title="Vorlage löschen"
                  className="p-2.5 rounded-xl text-slate-600 hover:text-red-400 hover:bg-red-500/10 transition-all"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
