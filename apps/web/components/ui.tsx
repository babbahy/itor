'use client';

import {
  Check,
  CircleAlert,
  CircleHelp,
  LoaderCircle,
  Minus,
  X,
} from 'lucide-react';
import { useEffect, useRef, type ReactNode } from 'react';
import { readinessCopy, serviceCopy } from '@/lib/presentation';
import type { ServiceStatus } from '@/lib/api';

export function Spinner() {
  return <LoaderCircle className="spin" size={17} aria-hidden="true" />;
}

export function Badge({
  children,
  tone = 'muted',
  dot = false,
}: {
  children: ReactNode;
  tone?: string;
  dot?: boolean;
}) {
  return (
    <span className={`badge badge-${tone}`}>
      {dot && <span className="status-dot" aria-hidden="true" />}
      {children}
    </span>
  );
}

export function StateBadge({ state }: { state: keyof typeof readinessCopy }) {
  const copy = readinessCopy[state];
  return (
    <Badge tone={copy.tone} dot>
      {copy.title}
    </Badge>
  );
}

export function ServiceBadge({
  service,
  connectedLabel,
}: {
  service: ServiceStatus | undefined;
  connectedLabel?: string;
}) {
  const copy = serviceCopy[service?.state ?? 'unknown'];
  return (
    <Badge tone={copy.tone} dot>
      {service?.state === 'connected' && connectedLabel
        ? connectedLabel
        : copy.label}
    </Badge>
  );
}

export function CheckMark({
  state,
}: {
  state: 'passed' | 'warning' | 'unknown' | 'unsupported';
}) {
  const Icon = {
    passed: Check,
    warning: CircleAlert,
    unknown: CircleHelp,
    unsupported: Minus,
  }[state];
  return (
    <span className={`check-mark mark-${state}`}>
      <Icon size={15} aria-hidden="true" />
    </span>
  );
}

export function Notice({
  children,
  kind = 'warning',
}: {
  children: ReactNode;
  kind?: 'warning' | 'error' | 'neutral';
}) {
  return (
    <div
      className={`notice notice-${kind}`}
      role={kind === 'error' ? 'alert' : 'status'}
    >
      <CircleAlert size={18} aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}

export function Dialog({
  title,
  children,
  onDismiss,
}: {
  title: string;
  children: ReactNode;
  onDismiss: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
    return () => {
      if (dialog?.open) dialog.close();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-label={title}
      onCancel={(event) => {
        event.preventDefault();
        onDismiss();
      }}
    >
      <div className="dialog-header">
        <h2>{title}</h2>
        <button
          className="icon-button"
          aria-label="Close dialog"
          onClick={onDismiss}
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
