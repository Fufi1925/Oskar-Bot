"use client";

/**
 * Auto Role.
 *
 * What this replaces: an English form with a plain <Select> per list, a
 * save button at the bottom of the left column, and no way to tell that
 * a role would never be handed out. The two things that actually break
 * this feature -- the bot's own role sitting below the one you picked,
 * and a role with dangerous permissions -- were not mentioned anywhere.
 *
 * Same shape as the other rebuilt tabs: one save bar for the whole page,
 * and leaving with an unsaved change is refused.
 */

import React from "react";
import {
  AlertTriangle, Bot, Info, ShieldAlert, Trash2, User, UserPlus,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { AutoRoleConfig, DiscordRole } from "@/types/api";
import { MultiRolePicker } from "@/components/dashboard/pickers";
import {
  StickySaveBar, useDraft, useSaveGuard,
} from "@/components/dashboard/save-bar";

/** Permissions that make handing a role to everyone a bad idea. */
const DANGEROUS: Array<[bigint, string]> = [
  [BigInt(0x8), "Administrator"],
  [BigInt(0x20), "Server verwalten"],
  [BigInt(0x10000000), "Rollen verwalten"],
  [BigInt(0x10), "Kanäle verwalten"],
  [BigInt(0x4), "Bannen"],
  [BigInt(0x2), "Kicken"],
  [BigInt(0x2000), "Nachrichten verwalten"],
];

function dangersOf(role: any): string[] {
  if (!role?.permissions) return [];
  let bits: bigint;
  try {
    bits = BigInt(role.permissions);
  } catch {
    return [];
  }
  return DANGEROUS.filter(([bit]) => (bits & bit) === bit).map(([, name]) => name);
}

function Card({ icon: Icon, title, subtitle, children }: any) {
  return (
    <div className="bg-[#10233f] border border-slate-800 rounded-3xl p-6 space-y-5">
      <div className="flex gap-3 min-w-0">
        <div className="h-10 w-10 rounded-2xl bg-primary/15 grid place-items-center shrink-0">
          <Icon className="h-5 w-5 text-primary" />
        </div>
        <div className="min-w-0">
          <p className="font-black text-white">{title}</p>
          {subtitle && (
            <p className="text-[12px] text-slate-400 mt-1 leading-relaxed">
              {subtitle}
            </p>
          )}
        </div>
      </div>
      {children}
    </div>
  );
}

function Warn({ children }: any) {
  return (
    <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/20 p-3.5 flex gap-2.5">
      <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
      <div className="text-[12px] text-amber-200/80 leading-relaxed">{children}</div>
    </div>
  );
}

export function AutoRoleForm({
  initialConfig,
  roles,
  guildId,
}: {
  initialConfig: AutoRoleConfig;
  roles: DiscordRole[];
  guildId: string;
}) {
  const d = useDraft<{ humans: string[]; bots: string[] }>({
    humans: initialConfig.humans || [],
    bots: initialConfig.bots || [],
  });
  const guard = useSaveGuard(d.dirty, "autorole-save-bar");

  const byId = (id: string) => roles.find((r) => String(r.id) === String(id));

  // The bot can only hand out roles below its own highest one. Discord
  // refuses silently otherwise, which is the single most common reason
  // this feature "does nothing". The API reports the bot's own top
  // position on every role; guessing it from "managed" roles would also
  // match every other bot's role.
  const botTop = roles[0]?.bot_top_position ?? 0;

  const problems = (ids: string[]) => {
    const out: string[] = [];
    for (const id of ids) {
      const role = byId(id);
      if (!role) {
        out.push(`Eine gewählte Rolle (${id}) gibt es nicht mehr.`);
        continue;
      }
      if (botTop > 0 && (role.position || 0) >= botTop) {
        out.push(
          `„${role.name}“ steht über der Bot-Rolle — Discord lässt den Bot ` +
            "sie nicht vergeben."
        );
      }
      const danger = dangersOf(role);
      if (danger.length) {
        out.push(
          `„${role.name}“ gibt jedem neuen Mitglied: ${danger.join(", ")}.`
        );
      }
    }
    return out;
  };

  const save = d.commit(async (values) => {
    if (values.humans.length > 10 || values.bots.length > 10) {
      throw new Error("Höchstens 10 Rollen je Liste.");
    }
    await api.updateAutoRole(guildId, {
      humans: values.humans,
      bots: values.bots,
    });
  });

  const List = ({
    field,
    title,
    hint,
    icon: Icon,
  }: {
    field: "humans" | "bots";
    title: string;
    hint: string;
    icon: any;
  }) => {
    const ids = d.value(field) || [];
    const issues = problems(ids);
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-primary/10 text-primary">
            <Icon className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h4 className="font-bold text-white text-sm">{title}</h4>
            <p className="text-[11px] text-slate-500 leading-relaxed">{hint}</p>
          </div>
          <span className="ml-auto text-[11px] font-black text-slate-500 shrink-0">
            {ids.length} / 10
          </span>
        </div>

        <MultiRolePicker
          guildId={guildId}
          value={ids}
          onChange={(next: string[]) => {
            if (next.length > 10) {
              toast.error("Höchstens 10 Rollen je Liste.");
              return;
            }
            d.set(field, next);
          }}
        />

        {issues.length > 0 && (
          <Warn>
            {issues.map((problem, i) => (
              <span key={i}>
                • {problem}
                <br />
              </span>
            ))}
          </Warn>
        )}
      </div>
    );
  };

  return (
    <section className="space-y-5">
      <Card
        icon={UserPlus}
        title="Rollen beim Beitritt"
        subtitle="Jeder, der auf den Server kommt, bekommt diese Rollen sofort — ohne dass jemand etwas tun muss."
      >
        <List
          field="humans"
          title="Für Mitglieder"
          hint="Menschen, die dem Server beitreten."
          icon={User}
        />

        <div className="border-t border-slate-800 pt-5">
          <List
            field="bots"
            title="Für Bots"
            hint="Andere Bots, die hinzugefügt werden."
            icon={Bot}
          />
        </div>
      </Card>

      <Card
        icon={Info}
        title="Woran es meistens scheitert"
        subtitle="Die drei Dinge, die diese Funktion still ausbremsen."
      >
        <div className="space-y-3 text-[12px] text-slate-400 leading-relaxed">
          <p className="flex gap-2.5">
            <ShieldAlert className="h-4 w-4 text-slate-600 shrink-0 mt-0.5" />
            <span>
              <b className="text-slate-200">Reihenfolge:</b> Die Bot-Rolle muss
              in den Server-Einstellungen <i>über</i> jeder Rolle stehen, die
              hier gewählt ist. Sonst lehnt Discord ab, ohne eine Meldung.
            </span>
          </p>
          <p className="flex gap-2.5">
            <ShieldAlert className="h-4 w-4 text-slate-600 shrink-0 mt-0.5" />
            <span>
              <b className="text-slate-200">Recht:</b> Der Bot braucht „Rollen
              verwalten“.
            </span>
          </p>
          <p className="flex gap-2.5">
            <ShieldAlert className="h-4 w-4 text-slate-600 shrink-0 mt-0.5" />
            <span>
              <b className="text-slate-200">Verifizierung:</b> Wenn dein Server
              eine Regel-Zustimmung verlangt, bekommt ein Mitglied Rollen erst,
              wenn es zugestimmt hat.
            </span>
          </p>
        </div>
      </Card>

      <StickySaveBar
        id="autorole-save-bar"
        count={d.dirty}
        busy={d.busy}
        shake={guard.shake}
        onDiscard={d.discard}
        onSave={save}
      />
    </section>
  );
}
