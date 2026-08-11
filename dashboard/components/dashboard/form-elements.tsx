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

import React from "react";
import { Switch } from "@/components/ui/switch";
import { Select, SelectOption } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

// --- ToggleSwitch ---
interface ToggleSwitchProps {
  label?: string;
  description?: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  className?: string;
}

export const ToggleSwitch = ({ 
  label, 
  description, 
  checked, 
  onCheckedChange, 
  disabled,
  className 
}: ToggleSwitchProps) => (
  <div className={cn("flex items-center justify-between gap-4 p-4 rounded-2xl bg-slate-900/30 border border-slate-800", className)}>
    {(label || description) && (
      <div className="flex flex-col">
        {label && <span className="text-sm font-bold text-slate-200">{label}</span>}
        {description && <span className="text-[11px] text-slate-500 font-medium italic mt-0.5">{description}</span>}
      </div>
    )}
    <Switch checked={checked} onCheckedChange={onCheckedChange} disabled={disabled} />
  </div>
);

// --- DropdownSelect ---
interface DropdownSelectProps {
  label?: string;
  value: string;
  onValueChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

export const DropdownSelect = ({ 
  label, 
  value, 
  onValueChange, 
  options, 
  placeholder, 
  disabled,
  className 
}: DropdownSelectProps) => (
  <div className={cn("space-y-2", className)}>
    {label && <label className="text-xs font-black uppercase text-slate-500 tracking-widest pl-1">{label}</label>}
    <Select 
      value={value} 
      onValueChange={onValueChange} 
      options={options} 
      placeholder={placeholder} 
      disabled={disabled}
    />
  </div>
);

// --- FormInput ---
interface FormInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  icon?: React.ElementType;
}

export const FormInput = ({ label, icon: Icon, className, ...props }: FormInputProps) => (
  <div className="space-y-2 w-full">
    {label && <label className="text-xs font-black uppercase text-slate-500 tracking-widest pl-1">{label}</label>}
    <div className="relative group">
      {Icon && (
        <Icon className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500 group-focus-within:text-primary transition-colors" />
      )}
      <Input 
        className={cn(
          "bg-slate-900/50 border-slate-800 rounded-xl h-12 focus:ring-primary/20",
          Icon && "pl-12",
          className
        )} 
        {...props} 
      />
    </div>
  </div>
);

/* ------------------------------------------------------------------ *
 * InlineToggle
 *
 * A switch with its label beside it, for use inside a form section
 * rather than as its own card.
 *
 * The three hand-rolled copies this replaces all had the same bug: the
 * thumb was `absolute` with no `left`, so it fell back to its static
 * position. A <button> centres its content, which put the thumb at
 * (44 - 16) / 2 = 14px instead of 4px — and `translate-x-6` then pushed
 * it to 38px, so 10px of a 44px track hung over the right edge and
 * covered the first letter of the label.
 *
 * Pinning it with `left-1` and moving it by the track width minus the
 * thumb minus both margins (44 - 16 - 4 - 4 = 20px = translate-x-5)
 * leaves an even 4px gap on both sides.
 * ------------------------------------------------------------------ */

interface InlineToggleProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: React.ReactNode;
  hint?: React.ReactNode;
  disabled?: boolean;
  className?: string;
}

/* ------------------------------------------------------------------ *
 * SwitchToggle
 *
 * Der nackte Schalter, ohne Beschriftung daneben — für Kopfzeilen, wo
 * der Text links steht und der Schalter rechts außen sitzt.
 *
 * Es gab davon drei handgeschriebene Kopien, und alle drei hatten
 * denselben Fehler wie die weiter oben beschriebenen: der Knopf war
 * `absolute` ohne `left`, fiel damit auf seine statische Position
 * zurück, und die zentriert ein <button>. Bei einer 48px-Bahn mit
 * 20px-Knopf sind das 14px statt 2px — `translate-x-6` schob ihn dann
 * auf 38px, also endete er bei 58px und hing 10px über den rechten
 * Rand hinaus. Genau so sah es auf dem gemeldeten Bild aus.
 *
 * `left-0.5` verankert ihn, und 48 − 20 − 2 − 2 = 24px = `translate-x-6`
 * lässt links wie rechts 2px stehen.
 * ------------------------------------------------------------------ */

interface SwitchToggleProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  label?: string;
  className?: string;
}

export const SwitchToggle = ({
  checked,
  onCheckedChange,
  disabled,
  label,
  className,
}: SwitchToggleProps) => (
  <button
    type="button"
    role="switch"
    aria-checked={!!checked}
    aria-label={label}
    disabled={disabled}
    onClick={() => !disabled && onCheckedChange(!checked)}
    className={cn(
      "relative h-6 w-12 rounded-full transition-colors shrink-0",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
      checked ? "bg-emerald-500" : "bg-slate-700",
      disabled && "opacity-40 cursor-not-allowed",
      className
    )}
  >
    <span
      className={cn(
        "absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform",
        checked ? "translate-x-6" : "translate-x-0"
      )}
    />
  </button>
);

export const InlineToggle = ({
  checked,
  onCheckedChange,
  label,
  hint,
  disabled,
  className,
}: InlineToggleProps) => (
  <label
    className={cn(
      "flex items-start gap-3",
      disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer",
      className
    )}
  >
    <button
      type="button"
      role="switch"
      aria-checked={!!checked}
      disabled={disabled}
      onClick={() => !disabled && onCheckedChange(!checked)}
      className={cn(
        "relative h-6 w-11 rounded-full transition-colors shrink-0 mt-0.5",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
        checked ? "bg-primary" : "bg-slate-700",
        disabled && "cursor-not-allowed"
      )}
    >
      <span
        className={cn(
          "absolute left-1 top-1 h-4 w-4 rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-5" : "translate-x-0"
        )}
      />
    </button>
    <span className="min-w-0">
      <span className="block text-sm text-slate-300">{label}</span>
      {hint && (
        <span className="block text-[11px] text-slate-600 mt-0.5 leading-relaxed">
          {hint}
        </span>
      )}
    </span>
  </label>
);
