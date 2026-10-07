"use client";

import * as React from "react";
import { Check, ChevronDown } from "lucide-react";
import { PopoverLayer } from "@/components/ui/popover-layer";
import { cn } from "@/lib/utils";

interface Option { value: string; label: React.ReactNode; text: string; disabled: boolean; group?: string }
function text(node: React.ReactNode): string {
  return React.Children.toArray(node).map(child => React.isValidElement(child)
    ? text((child.props as any).children) : String(child)).join("");
}
function optionsOf(children: React.ReactNode, group?: string, disabled = false): Option[] {
  return React.Children.toArray(children).flatMap(child => {
    if (!React.isValidElement(child)) return [];
    const props = child.props as any;
    if (child.type === "option") return [{ value: String(props.value ?? text(props.children)),
      label: props.children, text: text(props.children), disabled: disabled || Boolean(props.disabled), group }];
    return optionsOf(props.children, child.type === "optgroup" ? props.label : group, disabled || Boolean(props.disabled));
  });
}

/** Custom menu with a native form control preserving existing change handlers. */
export const WebsiteSelect = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  function WebsiteSelect({ children, className, style, id, onChange, value, defaultValue, disabled, multiple, ...props }, forwardedRef) {
    const native = React.useRef<HTMLSelectElement | null>(null);
    const anchor = React.useRef<HTMLDivElement>(null);
    const trigger = React.useRef<HTMLButtonElement>(null);
    const uid = React.useId();
    const options = optionsOf(children);
    const [selection, setSelection] = React.useState<string[]>(() => {
      const initial = value ?? defaultValue;
      return Array.isArray(initial) ? initial.map(String)
        : [String(initial ?? options.find(option => !option.disabled)?.value ?? "")];
    });
    const selected = value === undefined ? selection : (Array.isArray(value) ? value.map(String) : [String(value)]);
    const [open, setOpen] = React.useState(false);
    const [active, setActive] = React.useState(0);
    const typeahead = React.useRef({ text: "", at: 0 });
    const close = React.useCallback(() => setOpen(false), []);
    React.useEffect(() => { if (disabled) setOpen(false); }, [disabled]);

    const choose = (index: number) => {
      const option = options[index];
      if (!option || option.disabled || !native.current) return;
      const control = native.current;
      if (multiple) {
        for (const item of Array.from(control.options)) {
          item.selected = item.value === option.value ? !selected.includes(item.value) : selected.includes(item.value);
        }
      } else control.value = option.value;
      // The original React onChange receives a real select event and target.
      control.dispatchEvent(new Event("change", { bubbles: true }));
      if (!multiple) { setOpen(false); trigger.current?.focus(); }
    };
    const move = (direction: number) => {
      let index = active;
      for (let step = 0; step < options.length; step++) {
        index = (index + direction + options.length) % options.length;
        if (!options[index].disabled) { setActive(index); break; }
      }
    };
    const keyboard = (event: React.KeyboardEvent) => {
      if (event.key === "Escape") { setOpen(false); trigger.current?.focus(); return; }
      if (event.key === "Tab") { setOpen(false); return; }
      if (["ArrowDown", "ArrowUp", "Home", "End", "Enter", " "].includes(event.key)) {
        event.preventDefault();
        if (!open) { setActive(Math.max(0, options.findIndex(item => !item.disabled && selected.includes(item.value)))); setOpen(true); return; }
        if (event.key === "ArrowDown") move(1);
        else if (event.key === "ArrowUp") move(-1);
        else if (event.key === "Home") setActive(Math.max(0, options.findIndex(item => !item.disabled)));
        else if (event.key === "End") setActive(options.findLastIndex(item => !item.disabled));
        else choose(active);
      } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey) {
        const now = Date.now();
        typeahead.current.text = (now - typeahead.current.at > 700 ? "" : typeahead.current.text) + event.key.toLowerCase();
        typeahead.current.at = now;
        const index = options.findIndex(item => !item.disabled && item.text.toLowerCase().startsWith(typeahead.current.text));
        if (index >= 0) { setActive(index); setOpen(true); }
      }
    };
    React.useEffect(() => {
      if (open) document.getElementById(`${uid}-${active}`)?.scrollIntoView({ block: "nearest" });
    }, [open, active, uid]);

    return <div ref={anchor} className="relative min-w-0">
      <select {...props} ref={node => {
        native.current = node;
        if (typeof forwardedRef === "function") forwardedRef(node);
        else if (forwardedRef) forwardedRef.current = node;
      }} hidden aria-hidden="true" tabIndex={-1} value={value} defaultValue={defaultValue} disabled={disabled} multiple={multiple}
        onChange={event => { setSelection(Array.from(event.target.selectedOptions, item => item.value)); onChange?.(event); }}
        onInvalid={event => { event.preventDefault(); trigger.current?.focus(); props.onInvalid?.(event); }}>
        {children}
      </select>
      <button ref={trigger} id={id} type="button" disabled={disabled} role="combobox" aria-expanded={open}
        aria-controls={`${uid}-list`} aria-haspopup="listbox" aria-activedescendant={open ? `${uid}-${active}` : undefined}
        aria-label={props["aria-label"]} aria-labelledby={props["aria-labelledby"]} aria-required={props.required}
        style={style} onKeyDown={keyboard} onClick={() => { setActive(Math.max(0, options.findIndex(item => !item.disabled && selected.includes(item.value)))); setOpen(!open); }}
        className={cn("flex min-h-10 w-full items-center justify-between gap-3 rounded-xl border border-white/10 bg-[#18191c] px-4 py-2.5 text-left text-sm text-slate-200 outline-none transition focus:ring-2 focus:ring-primary/40 disabled:cursor-not-allowed disabled:opacity-50", className)}>
        <span className="min-w-0 truncate">{options.filter(option => selected.includes(option.value)).map(option => option.text).join(", ") || "—"}</span>
        <ChevronDown aria-hidden="true" className={cn("h-4 w-4 shrink-0 text-slate-500 transition-transform", open && "rotate-180")} />
      </button>
      <PopoverLayer anchor={anchor} open={open} onClose={close} maxHeight={300} className="rounded-xl border border-white/10 bg-[#202124] p-1.5 shadow-2xl">
        <div id={`${uid}-list`} role="listbox" aria-multiselectable={multiple || undefined} className="min-h-0 overflow-y-auto" onKeyDown={keyboard}>
          {options.map((option, index) => <React.Fragment key={`${option.value}-${index}`}>
            {option.group && option.group !== options[index - 1]?.group && <div className="px-3 pb-1 pt-3 text-xs font-semibold text-slate-500">{option.group}</div>}
            <button id={`${uid}-${index}`} type="button" role="option" aria-selected={selected.includes(option.value)} disabled={option.disabled}
              tabIndex={-1} onMouseEnter={() => setActive(index)} onClick={() => choose(index)}
              className={cn("flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition disabled:cursor-not-allowed disabled:opacity-40", active === index ? "bg-white/10 text-white" : "text-slate-300", selected.includes(option.value) && "text-primary")}>
              <span className="min-w-0 truncate">{option.label}</span>{selected.includes(option.value) && <Check aria-hidden="true" className="h-4 w-4 shrink-0" />}
            </button>
          </React.Fragment>)}
          {!options.length && <div className="p-3 text-sm text-slate-500">Keine Optionen</div>}
        </div>
      </PopoverLayer>
    </div>;
  }
);
