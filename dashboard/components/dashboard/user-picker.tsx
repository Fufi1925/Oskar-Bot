"use client";

import React, { useEffect, useRef, useState } from "react";
import { Loader2, Search, X } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PopoverLayer } from "@/components/ui/popover-layer";

interface Member {
  id: string;
  name: string;
  display_name: string;
  avatar: string;
  bot: boolean;
  top_role: string | null;
}

/**
 * Searchable member picker.
 *
 * Replaces the raw "paste a Discord ID" fields. Falls back to accepting a
 * plain ID so it still works when the member is not cached or no server is
 * selected yet.
 */
export function UserPicker({
  guildId,
  value,
  onChange,
  label = "User",
  placeholder = "Search by name or paste an ID",
}: {
  guildId?: string;
  value: string;
  onChange: (userId: string) => void;
  label?: string;
  placeholder?: string;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Member[]>([]);
  const [selected, setSelected] = useState<Member | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  // Das Eingabefeld ist der Anker: die Trefferliste haengt per Portal
  // an `document.body` und richtet sich daran aus. Klick daneben und
  // Escape erledigt `PopoverLayer` mit.
  const fieldRef = useRef<HTMLDivElement>(null);

  // Clear the chip when the value is reset from outside.
  useEffect(() => {
    if (!value) setSelected(null);
  }, [value]);

  // Debounced search so typing does not hammer the API.
  useEffect(() => {
    if (!guildId || !open) return;
    const handle = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await api.searchMembers(guildId, query);
        setResults(data.members || []);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => clearTimeout(handle);
  }, [query, guildId, open]);

  const pick = (member: Member) => {
    setSelected(member);
    onChange(member.id);
    setOpen(false);
    setQuery("");
  };

  const clear = () => {
    setSelected(null);
    onChange("");
    setQuery("");
  };

  return (
    <div className="space-y-2">
      <span className="text-xs font-black uppercase tracking-widest text-slate-500">{label}</span>

      {selected ? (
        <div className="flex items-center gap-3 bg-white/[0.03] border border-primary/30 rounded-2xl px-4 py-2.5">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={selected.avatar} alt="" className="h-7 w-7 rounded-lg" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-bold text-white truncate">{selected.display_name}</p>
            <code className="text-[10px] text-slate-500 font-mono">{selected.id}</code>
          </div>
          <button onClick={clear} className="text-slate-500 hover:text-white transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>
      ) : (
        <div className="relative" ref={fieldRef}>
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
          <input
            value={query}
            onFocus={() => setOpen(true)}
            onChange={(e) => {
              setQuery(e.target.value);
              setOpen(true);
              // A pasted ID is usable immediately, even without a match.
              if (/^\d{15,20}$/.test(e.target.value.trim())) {
                onChange(e.target.value.trim());
              }
            }}
            placeholder={guildId ? placeholder : "Select a server first"}
            disabled={!guildId}
            className="w-full bg-white/[0.03] border border-white/5 rounded-2xl pl-11 pr-4 py-3 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
          />

          <PopoverLayer
            anchor={fieldRef}
            open={open && !!guildId}
            onClose={() => setOpen(false)}
            maxHeight={288}
            className="bg-[#0a0a0c] border border-white/10 rounded-2xl shadow-2xl shadow-black/50"
          >
            <div className="flex-1 min-h-0 overflow-y-auto">
              {loading ? (
                <div className="flex items-center justify-center py-6">
                  <Loader2 className="h-5 w-5 text-primary animate-spin opacity-50" />
                </div>
              ) : results.length === 0 ? (
                <p className="text-xs text-slate-500 py-6 text-center">
                  {query ? "Keine Mitglieder gefunden." : "Tippen, um zu suchen."}
                </p>
              ) : (
                results.map((member) => (
                  <button
                    key={member.id}
                    onClick={() => pick(member)}
                    className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-white/[0.04] transition-colors text-left"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={member.avatar} alt="" className="h-7 w-7 rounded-lg shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-bold text-white truncate">
                          {member.display_name}
                        </p>
                        {member.bot && (
                          <span className="text-[9px] font-black uppercase px-1.5 py-0.5 rounded bg-primary/15 text-primary">
                            bot
                          </span>
                        )}
                      </div>
                      <code className="text-[10px] text-slate-500 font-mono">{member.id}</code>
                    </div>
                    {member.top_role && member.top_role !== "@everyone" && (
                      <span className="text-[10px] text-slate-600 shrink-0 truncate max-w-[90px]">
                        {member.top_role}
                      </span>
                    )}
                  </button>
                ))
              )}
            </div>
          </PopoverLayer>
        </div>
      )}
    </div>
  );
}
