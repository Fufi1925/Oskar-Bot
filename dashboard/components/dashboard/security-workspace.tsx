"use client";

import React from "react";
import { AlertTriangle, RefreshCw, type LucideIcon } from "lucide-react";

export function SecurityCard({
  icon: Icon,
  title,
  subtitle,
  children,
  onReload,
  reloadDisabled,
  tone,
}: {
  icon: LucideIcon;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  onReload?: () => void;
  reloadDisabled?: boolean;
  tone?: string;
}) {
  return (
    <section
      className={`cloudtix-settings-card cloudtix-security-card ${tone === "danger" ? "is-danger" : ""}`}
    >
      <div className="cloudtix-security-card-heading">
        <div className="cloudtix-settings-card-title">
          <span>
            <Icon size={19} />
          </span>
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
        </div>
        {onReload && (
          <button
            type="button"
            onClick={onReload}
            disabled={reloadDisabled}
            title="Aktualisieren"
            aria-label={`${title} aktualisieren`}
            className="cloudtix-settings-icon-button"
          >
            <RefreshCw size={16} />
          </button>
        )}
      </div>
      {children}
    </section>
  );
}

export function SecurityTabs({
  value,
  onChange,
  items,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  items: [string, string, LucideIcon][];
  label: string;
}) {
  return (
    <nav className="cloudtix-settings-tabs" aria-label={label}>
      {items.map(([id, title, Icon]) => (
        <button
          key={id}
          type="button"
          aria-pressed={id === value}
          onClick={() => onChange(id)}
        >
          <Icon size={15} />
          {title}
        </button>
      ))}
    </nav>
  );
}

export function SecurityMetrics({
  items,
}: {
  items: {
    label: string;
    value: React.ReactNode;
    icon: LucideIcon;
    note: string;
  }[];
}) {
  return (
    <div className="cloudtix-settings-metrics cloudtix-security-metrics">
      {items.map(({ label, value, icon: Icon, note }) => (
        <div key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
          <small>{note}</small>
          <Icon size={20} />
        </div>
      ))}
    </div>
  );
}

export function SecurityWarnings({ items }: { items?: string[] }) {
  if (!items?.length) return null;
  return (
    <div className="cloudtix-settings-warning">
      <AlertTriangle size={18} />
      <div>
        <strong>Konfiguration prüfen</strong>
        {items.map((item, i) => (
          <p key={i}>{item}</p>
        ))}
      </div>
    </div>
  );
}

export function SecurityField({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="cloudtix-security-field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </div>
  );
}
