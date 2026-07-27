"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Hash, Loader2, Search, Volume2, X } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ *
 * Shared cache
 *
 * Several forms on the same page ask for the same roles and channels.
 * Fetching once per guild keeps the dashboard from firing the same
 * request five times on mount.
 * ------------------------------------------------------------------ */
const cache = new Map<string, Promise<any[]>>();

function load(kind: "roles" | "channels", guildId?: string): Promise<any[]> {
  if (!guildId) return Promise.resolve([]);
  const key = `${kind}:${guildId}`;
  if (!cache.has(key)) {
    const p = (kind === "roles" ? api.getRoles(guildId) : api.getChannels(guildId))
      .then((r: any) => (Array.isArray(r) ? r : []))
      .catch(() => []);
    cache.set(key, p);
  }
  return cache.get(key)!;
}

/** Drop the cache so a picker re-reads after roles/channels changed. */
export function invalidatePickerCache(guildId?: string) {
  if (!guildId) return cache.clear();
  cache.delete(`roles:${guildId}`);
  cache.delete(`channels:${guildId}`);
}

function useOutsideClose(ref: React.RefObject<HTMLElement>, close: () => void) {
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [ref, close]);
}

function roleColor(color?: number) {
  if (!color) return "#99aab5";
  return `#${color.toString(16).padStart(6, "0")}`;
}

/* ------------------------------------------------------------------ *
 * Single select (channel or role)
 * ------------------------------------------------------------------ */
function SinglePicker({
  kind,
  guildId,
  value,
  onChange,
  placeholder,
  disabled,
  allowClear = true,
  channelTypes,
}: {
  kind: "roles" | "channels";
  guildId?: string;
  value: string | number | null | undefined;
  onChange: (id: string | null) => void;
  placeholder?: string;
  disabled?: boolean;
  allowClear?: boolean;
  channelTypes?: string[];
}) {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const box = useRef<HTMLDivElement>(null);
  useOutsideClose(box, () => setOpen(false));

  useEffect(() => {
    if (!guildId) return;
    setLoading(true);
    load(kind, guildId)
      .then(setItems)
      .finally(() => setLoading(false));
  }, [kind, guildId]);

  const usable = useMemo(() => {
    let list = items;
    if (kind === "channels" && channelTypes?.length) {
      list = list.filter((c) => channelTypes.includes(String(c.type)));
    }
    if (kind === "roles") {
      // @everyone is never a useful choice here.
      list = list.filter((r) => r.name !== "@everyone");
    }
    const q = query.trim().toLowerCase();
    return q ? list.filter((i) => String(i.name).toLowerCase().includes(q)) : list;
  }, [items, query, kind, channelTypes]);

  const current = items.find((i) => String(i.id) === String(value ?? ""));

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        disabled={disabled || !guildId}
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "w-full flex items-center justify-between gap-2 rounded-xl border px-4 py-3 text-left transition-colors",
          "bg-[#0d1b31] border-slate-800 hover:border-slate-700",
          (disabled || !guildId) && "opacity-50 cursor-not-allowed"
        )}
      >
        <span className="flex items-center gap-2 min-w-0">
          {current ? (
            kind === "roles" ? (
              <>
                <span
                  className="h-3 w-3 rounded-full shrink-0"
                  style={{ background: roleColor(current.color) }}
                />
                <span className="truncate text-sm text-white">{current.name}</span>
              </>
            ) : (
              <>
                {String(current.type) === "2" ? (
                  <Volume2 className="h-4 w-4 text-slate-500 shrink-0" />
                ) : (
                  <Hash className="h-4 w-4 text-slate-500 shrink-0" />
                )}
                <span className="truncate text-sm text-white">{current.name}</span>
              </>
            )
          ) : (
            <span className="truncate text-sm text-slate-500">
              {loading
                ? "Loading…"
                : !guildId
                ? "Select a server first"
                : placeholder || `Select ${kind === "roles" ? "a role" : "a channel"}`}
            </span>
          )}
        </span>

        <span className="flex items-center gap-1 shrink-0">
          {loading && <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-500" />}
          {allowClear && current && !disabled && (
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => {
                e.stopPropagation();
                onChange(null);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.stopPropagation();
                  onChange(null);
                }
              }}
              className="p-0.5 rounded hover:bg-white/10 text-slate-500 hover:text-slate-300"
            >
              <X className="h-3.5 w-3.5" />
            </span>
          )}
          <ChevronDown className="h-4 w-4 text-slate-500" />
        </span>
      </button>

      {open && (
        <div className="absolute z-50 mt-2 w-full rounded-xl border border-slate-800 bg-[#0d1b31] shadow-2xl overflow-hidden">
          {items.length > 8 && (
            <div className="relative border-b border-slate-800">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search…"
                className="w-full bg-transparent pl-9 pr-3 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none"
              />
            </div>
          )}

          <div className="max-h-64 overflow-y-auto py-1">
            {usable.length === 0 ? (
              <p className="px-4 py-6 text-center text-xs text-slate-500">
                {loading ? "Loading…" : "Nothing found."}
              </p>
            ) : (
              usable.map((item) => {
                const active = String(item.id) === String(value ?? "");
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      onChange(String(item.id));
                      setOpen(false);
                      setQuery("");
                    }}
                    className={cn(
                      "w-full flex items-center gap-2 px-4 py-2.5 text-left text-sm transition-colors",
                      active ? "bg-primary/15 text-primary" : "text-slate-300 hover:bg-white/5"
                    )}
                  >
                    {kind === "roles" ? (
                      <span
                        className="h-3 w-3 rounded-full shrink-0"
                        style={{ background: roleColor(item.color) }}
                      />
                    ) : String(item.type) === "2" ? (
                      <Volume2 className="h-4 w-4 text-slate-500 shrink-0" />
                    ) : (
                      <Hash className="h-4 w-4 text-slate-500 shrink-0" />
                    )}
                    <span className="truncate flex-1">{item.name}</span>
                    {active && <Check className="h-3.5 w-3.5 shrink-0" />}
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function ChannelPicker(props: Omit<Parameters<typeof SinglePicker>[0], "kind">) {
  return <SinglePicker kind="channels" {...props} />;
}

export function RolePicker(props: Omit<Parameters<typeof SinglePicker>[0], "kind">) {
  return <SinglePicker kind="roles" {...props} />;
}

/* ------------------------------------------------------------------ *
 * Multi select — replaces the "ID1, ID2, ..." text fields
 * ------------------------------------------------------------------ */
export function MultiRolePicker({
  guildId,
  value,
  onChange,
  placeholder = "Select roles",
  disabled,
}: {
  guildId?: string;
  value: Array<string | number>;
  onChange: (ids: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const box = useRef<HTMLDivElement>(null);
  useOutsideClose(box, () => setOpen(false));

  useEffect(() => {
    if (!guildId) return;
    setLoading(true);
    load("roles", guildId)
      .then(setItems)
      .finally(() => setLoading(false));
  }, [guildId]);

  const selected = (value || []).map(String);
  const usable = useMemo(() => {
    const list = items.filter((r) => r.name !== "@everyone");
    const q = query.trim().toLowerCase();
    return q ? list.filter((r) => String(r.name).toLowerCase().includes(q)) : list;
  }, [items, query]);

  const toggle = (id: string) =>
    onChange(
      selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id]
    );

  return (
    <div ref={box} className="relative">
      <div
        onClick={() => !disabled && guildId && setOpen((o) => !o)}
        className={cn(
          "w-full min-h-[48px] flex items-center gap-2 flex-wrap rounded-xl border px-3 py-2 cursor-pointer transition-colors",
          "bg-[#0d1b31] border-slate-800 hover:border-slate-700",
          (disabled || !guildId) && "opacity-50 cursor-not-allowed"
        )}
      >
        {selected.length === 0 && (
          <span className="text-sm text-slate-500 px-1">
            {loading ? "Loading…" : !guildId ? "Select a server first" : placeholder}
          </span>
        )}

        {selected.map((id) => {
          const role = items.find((r) => String(r.id) === id);
          return (
            <span
              key={id}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/[0.06] border border-white/10 text-xs text-slate-200"
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: roleColor(role?.color) }}
              />
              {role?.name || id}
              {!disabled && (
                <X
                  className="h-3 w-3 text-slate-500 hover:text-red-400"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggle(id);
                  }}
                />
              )}
            </span>
          );
        })}

        <ChevronDown className="h-4 w-4 text-slate-500 ml-auto shrink-0" />
      </div>

      {open && (
        <div className="absolute z-50 mt-2 w-full rounded-xl border border-slate-800 bg-[#0d1b31] shadow-2xl overflow-hidden">
          {items.length > 8 && (
            <div className="relative border-b border-slate-800">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search…"
                className="w-full bg-transparent pl-9 pr-3 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none"
              />
            </div>
          )}
          <div className="max-h-64 overflow-y-auto py-1">
            {usable.length === 0 ? (
              <p className="px-4 py-6 text-center text-xs text-slate-500">
                {loading ? "Loading…" : "No roles found."}
              </p>
            ) : (
              usable.map((role) => {
                const active = selected.includes(String(role.id));
                return (
                  <button
                    key={role.id}
                    type="button"
                    onClick={() => toggle(String(role.id))}
                    className={cn(
                      "w-full flex items-center gap-2 px-4 py-2.5 text-left text-sm transition-colors",
                      active ? "bg-primary/15 text-primary" : "text-slate-300 hover:bg-white/5"
                    )}
                  >
                    <span
                      className="h-3 w-3 rounded-full shrink-0"
                      style={{ background: roleColor(role.color) }}
                    />
                    <span className="truncate flex-1">{role.name}</span>
                    {active && <Check className="h-3.5 w-3.5 shrink-0" />}
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
