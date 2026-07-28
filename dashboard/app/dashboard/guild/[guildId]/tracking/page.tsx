/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║                                                                  ║
 * ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
 * ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
 * ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
 * ║                                                                  ║
 * ║           © 2026 University Bot Devs — All Rights Reserved               ║
 * ║                                                                  ║
 * ║   discord  ──  https://discord.gg/MG3rYnUZJV                      ║
 * ║   youtube  ──  https://youtube.com/@University BotDevs                   ║
 * ║   github   ──  https://github.com/University Bot                        ║
 * ║                                                                  ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

"use client";

import React, { useState, useEffect } from "react";
import { Search, Save, RefreshCcw, Bell } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { ChannelPicker } from "@/components/dashboard/pickers";
import { StickySaveBar, useSaveGuard } from "@/components/dashboard/save-bar";

export default function TrackingPage({ params }: { params: { guildId: string } }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [channels, setChannels] = useState<any[]>([]);
  const [config, setConfig] = useState<any>({ channel_id: null });
  const [saved, setSaved] = useState<any>({ channel_id: null });

  const fetchData = async () => {
    try {
      setLoading(true);
      const [configData, channelsData] = await Promise.all([
        api.getTracking(params.guildId),
        api.getChannels(params.guildId),
      ]);
      setConfig(configData);
      setSaved(configData);
      setChannels(channelsData);
    } catch (error) {
      console.error("Failed to fetch tracking data:", error);
      toast.error("Failed to load tracking configuration");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [params.guildId]);

  const dirty =
    String(config.channel_id ?? "") === String(saved.channel_id ?? "") ? 0 : 1;
  const guard = useSaveGuard(dirty, "tracking-save-bar");

  const handleSave = async () => {
    try {
      setSaving(true);
      await api.updateTracking(params.guildId, {
        channel_id: config.channel_id || null,
      });
      setSaved(config);
      toast.success("Gespeichert.");
    } catch (error: any) {
      toast.error(error?.message || "Speichern fehlgeschlagen.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <RefreshCcw className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight">Invite Tracking</h2>
        <p className="text-muted-foreground">
          Configure where the bot logs invite information when a member joins.
        </p>
      </div>

      <Card className="border-primary/20 bg-background/50 backdrop-blur-xl">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Search className="w-5 h-5 text-primary" />
            <CardTitle>Logging Configuration</CardTitle>
          </div>
          <CardDescription>
            Choose a channel to receive notifications about member invites and join sources.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <Label>Log Channel</Label>
            {/* parseInt() here used to round the snowflake: a 19-digit
                id past 2**53 came back off by a hundred or so, and the
                save pointed at a channel that does not exist. */}
            <ChannelPicker
              guildId={params.guildId}
              value={config.channel_id ? String(config.channel_id) : ""}
              onChange={(id: string | null) =>
                setConfig({ ...config, channel_id: id })
              }
              placeholder="Kein Protokoll"
              channelTypes={["0", "5"]}
            />
          </div>

        </CardContent>
      </Card>

      <Card className="border-yellow-500/20 bg-yellow-500/5">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Bell className="w-5 h-5 text-yellow-500" />
            <CardTitle className="text-yellow-500">Information</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            The invite tracking module monitors all join events and attempts to identify which invite link was used.
            This information is then logged to your chosen channel.
          </p>
        </CardContent>
      </Card>

      <StickySaveBar
        id="tracking-save-bar"
        count={dirty}
        busy={saving}
        shake={guard.shake}
        onDiscard={() => setConfig(saved)}
        onSave={handleSave}
      />
    </div>
  );
}
